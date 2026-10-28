//! Streaming decode/resampling on worker threads; never called by the callback.
use rubato::{
    Resampler, SincFixedIn, SincInterpolationParameters, SincInterpolationType, WindowFunction,
};
use std::{fs::File, path::Path};
use symphonia::core::{
    audio::SampleBuffer, codecs::DecoderOptions, errors::Error, formats::FormatOptions,
    io::MediaSourceStream, meta::MetadataOptions, probe::Hint,
};

pub type Frame = [f32; 2];
pub type Result<T> = std::result::Result<T, String>;

fn open(path: &Path) -> Result<Box<dyn symphonia::core::formats::FormatReader>> {
    let file = File::open(path).map_err(|e| e.to_string())?;
    let mut hint = Hint::new();
    if let Some(ext) = path.extension().and_then(|s| s.to_str()) {
        hint.with_extension(ext);
    }
    symphonia::default::get_probe()
        .format(
            &hint,
            MediaSourceStream::new(Box::new(file), Default::default()),
            // Honour encoder delay/padding (especially MP3) so duration and
            // audition timing exclude codec-added leading/trailing silence.
            &FormatOptions {
                enable_gapless: true,
                ..FormatOptions::default()
            },
            &MetadataOptions::default(),
        )
        .map(|r| r.format)
        .map_err(|e| e.to_string())
}

/// Read duration/rate/channel metadata without decoding the entire source.
pub fn probe(path: &Path) -> Result<(u32, u64, usize)> {
    let format = open(path)?;
    let params = &format.default_track().ok_or("No audio track")?.codec_params;
    Ok((
        params.sample_rate.ok_or("Missing sample rate")?,
        params.n_frames.unwrap_or(0),
        params.channels.ok_or("Missing channels")?.count(),
    ))
}

/// Decode bounded packets and feed device-rate stereo blocks to a cancellable sink.
/// Seek is performed by the format reader; any lead-in is discarded after resampling.
pub fn stream(
    path: &Path,
    start: f64,
    rate: u32,
    mut sink: impl FnMut(&[Frame]) -> Result<bool>,
) -> Result<()> {
    use symphonia::core::{
        formats::{SeekMode, SeekTo},
        units::Time,
    };
    let mut format = open(path)?;
    let track = format.default_track().ok_or("No audio track")?;
    let track_id = track.id;
    let params = track.codec_params.clone();
    let source_rate = params.sample_rate.ok_or("Missing sample rate")?;
    let expected = params
        .n_frames
        .map(|n| ((n as f64 / source_rate as f64 - start).max(0.0) * rate as f64).round() as usize);
    let mut decoder = symphonia::default::get_codecs()
        .make(&params, &DecoderOptions::default())
        .map_err(|e| e.to_string())?;
    let mut skip = 0;
    if start > 0.0 {
        let seek = format
            .seek(
                SeekMode::Accurate,
                SeekTo::Time {
                    time: Time::from(start),
                    track_id: Some(track_id),
                },
            )
            .map_err(|e| e.to_string())?;
        let actual = params.time_base.map(|tb| tb.calc_time(seek.actual_ts));
        let actual_s = actual.map(|t| t.seconds as f64 + t.frac).unwrap_or(0.0);
        skip = ((start - actual_s).max(0.0) * rate as f64).round() as usize;
        decoder.reset();
    }
    let mut resampler = if source_rate == rate {
        None
    } else {
        Some(
            SincFixedIn::<f32>::new(
                rate as f64 / source_rate as f64,
                2.0,
                SincInterpolationParameters {
                    sinc_len: 128,
                    f_cutoff: 0.95,
                    interpolation: SincInterpolationType::Linear,
                    oversampling_factor: 128,
                    window: WindowFunction::BlackmanHarris2,
                },
                1024,
                2,
            )
            .map_err(|e| e.to_string())?,
        )
    };
    skip += resampler.as_ref().map(|r| r.output_delay()).unwrap_or(0);
    let mut pending = [Vec::with_capacity(1024), Vec::with_capacity(1024)];
    let mut emitted = 0;
    // All buffers/closures here belong to a decoder worker; callback memory is fixed.
    let mut emit = |frames: &[Frame]| -> Result<bool> {
        let dropped = skip.min(frames.len());
        skip -= dropped;
        let frames = &frames[dropped..];
        let count = expected
            .map(|n| n.saturating_sub(emitted).min(frames.len()))
            .unwrap_or(frames.len());
        emitted += count;
        if count != 0 && !sink(&frames[..count])? {
            return Ok(false);
        }
        Ok(expected.map(|n| emitted < n).unwrap_or(true))
    };
    loop {
        let packet = match format.next_packet() {
            Ok(p) => p,
            Err(Error::IoError(e)) if e.kind() == std::io::ErrorKind::UnexpectedEof => break,
            Err(e) => return Err(e.to_string()),
        };
        if packet.track_id() != track_id {
            continue;
        }
        let audio = decoder.decode(&packet).map_err(|e| e.to_string())?;
        let channels = audio.spec().channels.count();
        let mut samples = SampleBuffer::<f32>::new(audio.capacity() as u64, *audio.spec());
        samples.copy_interleaved_ref(audio);
        if let Some(resampler) = resampler.as_mut() {
            for frame in samples.samples().chunks(channels) {
                pending[0].push(frame[0]);
                pending[1].push(frame[if channels > 1 { 1 } else { 0 }]);
                if pending[0].len() == 1024 {
                    let output = resampler
                        .process(&pending, None)
                        .map_err(|e| e.to_string())?;
                    let frames: Vec<Frame> = output[0]
                        .iter()
                        .zip(&output[1])
                        .map(|(&l, &r)| [l, r])
                        .collect();
                    if !emit(&frames)? {
                        return Ok(());
                    }
                    pending.iter_mut().for_each(Vec::clear);
                }
            }
        } else {
            let frames: Vec<Frame> = samples
                .samples()
                .chunks(channels)
                .map(|f| [f[0], f[if channels > 1 { 1 } else { 0 }]])
                .collect();
            if !emit(&frames)? {
                return Ok(());
            }
        }
    }
    if let Some(resampler) = resampler.as_mut() {
        // Flush filter delay using one padded final block, clipped by expected duration.
        let output = resampler
            .process_partial(Some(&pending), None)
            .map_err(|e| e.to_string())?;
        let frames: Vec<Frame> = output[0]
            .iter()
            .zip(&output[1])
            .map(|(&l, &r)| [l, r])
            .collect();
        if emit(&frames)? {
            let output = resampler
                .process_partial::<Vec<f32>>(None, None)
                .map_err(|e| e.to_string())?;
            let frames: Vec<Frame> = output[0]
                .iter()
                .zip(&output[1])
                .map(|(&l, &r)| [l, r])
                .collect();
            emit(&frames)?;
        }
    }
    Ok(())
}
