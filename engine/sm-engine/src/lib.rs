//! Optional audition engine. Control/decoder threads own all allocation and I/O.
//! The device callback consumes bounded SPSC rings, mixes two voices and publishes
//! atomic observations. Retired voice allocations return to the control thread.
mod decoder;
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use crossbeam_channel::{bounded, Receiver, Sender};
pub use decoder::probe;
use decoder::{Frame, Result};
use rtrb::{Consumer, Producer, RingBuffer};
use std::{
    collections::{HashMap, VecDeque},
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering::*},
        Arc, Mutex,
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant, SystemTime},
};

#[derive(Default)]
struct State {
    generation: AtomicU64,
    prefetch_generation: AtomicU64,
    token: AtomicU64,
    position: AtomicU64,
    status: AtomicU32,
    peak: AtomicU32,
    rms: AtomicU32,
    starved: AtomicU64,
    xruns: AtomicU64,
    complete: AtomicU64,
    quit: AtomicBool,
    command_ns: AtomicU64,
    ready_ns: AtomicU64,
    out_ns: AtomicU64,
}

/// Eventually consistent, nonblocking observations; times share the engine clock.
pub struct Snapshot {
    pub now_ns: u64,
    pub token: u64,
    pub position: u64,
    pub status: u32,
    pub peak: f32,
    pub rms: f32,
    pub xruns: u64,
    pub starved: u64,
    pub command_ns: u64,
    pub ready_ns: u64,
    pub out_ns: u64,
}

struct Voice {
    generation: u64,
    token: u64,
    cursor: u64,
    gain: f32,
    frames: Consumer<Frame>,
    done: Arc<AtomicBool>,
}

/// All fields needed by the callback are preallocated before the stream starts.
struct Callback {
    incoming: Consumer<Voice>,
    retired: Producer<Voice>,
    voices: [Option<Voice>; 2],
    state: Arc<State>,
    fade_step: f32,
    clock: Instant,
}

impl Callback {
    fn retire(&mut self, voice: Voice) {
        // Previous queue + current batch + active voices total at most 18.
        // Capacity 32 is larger; control drains before every bounded batch.
        assert!(self.retired.push(voice).is_ok(), "retirement invariant");
    }

    fn render<T: cpal::Sample + cpal::FromSample<f32>>(&mut self, out: &mut [T], channels: usize) {
        // No Vec growth, locks, file I/O or Python work occurs in this function.
        while let Ok(voice) = self.incoming.pop() {
            if voice.generation != self.state.generation.load(Acquire) {
                self.retire(voice);
                continue;
            }
            if let Some(old) = self.voices[1].take() {
                self.retire(old);
            }
            self.voices[1] = self.voices[0].take();
            self.voices[0] = Some(voice);
        }
        let generation = self.state.generation.load(Acquire);
        let mut peak = 0.0_f32;
        let mut power = 0.0_f64;
        let mut starved = false;
        for output in out.chunks_mut(channels) {
            let mut mixed = [0.0_f32; 2];
            for slot in 0..2 {
                let mut remove = false;
                if let Some(voice) = self.voices[slot].as_mut() {
                    let active = slot == 0 && voice.generation == generation;
                    voice.gain = if active {
                        (voice.gain + self.fade_step).min(1.0)
                    } else {
                        (voice.gain - self.fade_step).max(0.0)
                    };
                    match voice.frames.pop() {
                        Ok(frame) => {
                            mixed[0] += frame[0] * voice.gain;
                            mixed[1] += frame[1] * voice.gain;
                            voice.cursor += 1;
                            if active {
                                self.state.position.store(voice.cursor, Relaxed);
                                if self.state.out_ns.load(Relaxed) == 0
                                    && frame.iter().any(|v| *v != 0.0)
                                {
                                    let _ = self.state.out_ns.compare_exchange(
                                        0,
                                        self.clock.elapsed().as_nanos() as u64,
                                        Relaxed,
                                        Relaxed,
                                    );
                                }
                                let _ = self.state.status.compare_exchange(1, 2, AcqRel, Acquire);
                            }
                        }
                        Err(_) => {
                            if voice.done.load(Acquire) {
                                remove = true;
                                if active {
                                    self.state.complete.store(voice.token, Release);
                                    if self.state.status.load(Relaxed) != 4 {
                                        self.state.status.store(0, Release);
                                    }
                                }
                            } else if active {
                                starved = true;
                            }
                        }
                    }
                    remove |= !active && voice.gain == 0.0;
                }
                if remove {
                    if let Some(voice) = self.voices[slot].take() {
                        self.retire(voice);
                    }
                }
            }
            for (ch, sample) in output.iter_mut().enumerate() {
                let value = if channels == 1 {
                    (mixed[0] + mixed[1]) * 0.5
                } else if ch < 2 {
                    mixed[ch]
                } else {
                    0.0
                };
                let value = value.clamp(-1.0, 1.0);
                peak = peak.max(value.abs());
                power += f64::from(value) * f64::from(value);
                *sample = T::from_sample(value);
            }
        }
        self.state.peak.store(peak.to_bits(), Relaxed);
        self.state.rms.store(
            ((power / out.len().max(1) as f64).sqrt() as f32).to_bits(),
            Relaxed,
        );
        if starved {
            self.state.starved.fetch_add(1, Relaxed);
        }
    }
}

#[derive(Clone)]
enum Source {
    Path(PathBuf),
    Pcm(Arc<Vec<Frame>>),
}
#[derive(Clone)]
struct Job {
    generation: u64,
    token: u64,
    source: Source,
    start: f64,
    prefetch: bool,
}
type CacheKey = (PathBuf, u64, SystemTime);
struct Head {
    frames: Arc<Vec<Frame>>,
    complete: bool,
}
struct Cache {
    entries: HashMap<CacheKey, Head>,
    order: VecDeque<CacheKey>,
    bytes: usize,
    limit: usize,
}

impl Cache {
    fn get(&mut self, key: &CacheKey) -> Option<(Arc<Vec<Frame>>, bool)> {
        let value = self
            .entries
            .get(key)
            .map(|h| (h.frames.clone(), h.complete))?;
        self.order.retain(|old| old != key);
        self.order.push_back(key.clone());
        Some(value)
    }

    fn insert(&mut self, key: CacheKey, frames: Vec<Frame>, complete: bool) {
        if self.entries.contains_key(&key) {
            return;
        }
        self.bytes += frames.len() * 8;
        self.order.push_back(key.clone());
        self.entries.insert(
            key,
            Head {
                frames: Arc::new(frames),
                complete,
            },
        );
        while self.bytes > self.limit {
            if let Some(key) = self.order.pop_front() {
                if let Some(head) = self.entries.remove(&key) {
                    self.bytes -= head.frames.len() * 8;
                }
            } else {
                break;
            }
        }
    }
}
fn key(path: &PathBuf) -> Option<CacheKey> {
    let metadata = std::fs::metadata(path).ok()?;
    Some((path.clone(), metadata.len(), metadata.modified().ok()?))
}

/// Narrow control boundary. Workers/stream are optional; NullBackend uses the same callback.
pub struct Engine {
    state: Arc<State>,
    jobs: Sender<Job>,
    prefetch: Sender<Job>,
    errors: Arc<Mutex<VecDeque<(u64, String)>>>,
    thread: Option<JoinHandle<()>>,
    pub rate: u32,
    pub channels: usize,
    last_complete: u64,
    clock: Instant,
}

impl Engine {
    /// Device names are mapped at the Python boundary, never by PortAudio index.
    pub fn devices() -> Result<Vec<String>> {
        cpal::default_host()
            .output_devices()
            .map_err(|e| e.to_string())?
            .map(|device| device.name().map_err(|e| e.to_string()))
            .collect()
    }

    pub fn new(
        device: Option<usize>,
        buffer_frames: u32,
        cache_mb: usize,
        null: bool,
    ) -> Result<Self> {
        let state = Arc::new(State::default());
        let errors = Arc::new(Mutex::new(VecDeque::new()));
        let (jobs_tx, jobs_rx) = bounded(2);
        let (pre_tx, pre_rx) = bounded(16);
        let (ready_tx, ready_rx) = bounded::<Voice>(2);
        let (init_tx, init_rx) = bounded(1);
        let control_state = state.clone();
        let control_errors = errors.clone();
        let clock = Instant::now();
        let handle = thread::spawn(move || {
            let run = || -> Result<()> {
                let host = cpal::default_host();
                let device = if null {
                    None
                } else {
                    Some(match device {
                        Some(index) => host
                            .output_devices()
                            .map_err(|e| e.to_string())?
                            .nth(index)
                            .ok_or("Device unavailable")?,
                        None => host
                            .default_output_device()
                            .ok_or("No default output device")?,
                    })
                };
                let config = device
                    .as_ref()
                    .map(|d| d.default_output_config().map_err(|e| e.to_string()))
                    .transpose()?;
                let rate = config.as_ref().map(|c| c.sample_rate().0).unwrap_or(48000);
                let channels = config.as_ref().map(|c| c.channels() as usize).unwrap_or(2);
                let (mut incoming_tx, incoming_rx) = RingBuffer::new(8);
                let (retired_tx, mut retired_rx) = RingBuffer::new(32);
                let mut callback = Some(Callback {
                    incoming: incoming_rx,
                    retired: retired_tx,
                    voices: [None, None],
                    state: control_state.clone(),
                    fade_step: 1.0 / (rate as f32 * 0.003),
                    clock,
                });
                let mut stream = None;
                if let (Some(device), Some(config)) = (device, config) {
                    let mut stream_config: cpal::StreamConfig = config.clone().into();
                    stream_config.buffer_size = cpal::BufferSize::Fixed(buffer_frames);
                    let cb = callback.take().unwrap();
                    let audio = match config.sample_format() {
                        cpal::SampleFormat::F32 => open_stream::<f32>(&device, &stream_config, cb)?,
                        cpal::SampleFormat::I16 => open_stream::<i16>(&device, &stream_config, cb)?,
                        cpal::SampleFormat::U16 => open_stream::<u16>(&device, &stream_config, cb)?,
                        _ => return Err("Unsupported device sample format".into()),
                    };
                    audio.play().map_err(|e| e.to_string())?;
                    stream = Some(audio);
                }
                let cache = Arc::new(Mutex::new(Cache {
                    entries: HashMap::new(),
                    order: VecDeque::new(),
                    bytes: 0,
                    limit: cache_mb * 1024 * 1024,
                }));
                let workers: Vec<_> = (0..2)
                    .map(|_| {
                        let args = (
                            jobs_rx.clone(),
                            pre_rx.clone(),
                            ready_tx.clone(),
                            control_state.clone(),
                            control_errors.clone(),
                            cache.clone(),
                        );
                        thread::spawn(move || {
                            worker(args.0, args.1, args.2, args.3, args.4, args.5, rate, clock)
                        })
                    })
                    .collect();
                init_tx
                    .send(Ok((rate, channels)))
                    .map_err(|e| e.to_string())?;
                let mut null_buffer = vec![0.0; buffer_frames as usize * channels];
                let period = Duration::from_secs_f64(buffer_frames as f64 / rate as f64);
                while !control_state.quit.load(Acquire) {
                    // Reclamation happens here, never in the real-time callback.
                    while retired_rx.pop().is_ok() {}
                    // Bound each publication batch so retirement capacity remains
                    // provable even under an adversarial continuous command stream.
                    for _ in 0..8 {
                        let Ok(voice) = ready_rx.try_recv() else {
                            break;
                        };
                        if voice.generation == control_state.generation.load(Acquire) {
                            if let Err(rtrb::PushError::Full(_voice)) = incoming_tx.push(voice) {
                                return Err("Callback command ring full".into());
                            }
                        }
                    }
                    if let Some(callback) = callback.as_mut() {
                        callback.render(&mut null_buffer, channels);
                        thread::sleep(period);
                    } else {
                        thread::sleep(Duration::from_millis(2));
                    }
                }
                drop(stream);
                for worker in workers {
                    let _ = worker.join();
                }
                Ok(())
            };
            if let Err(error) = run() {
                control_state.quit.store(true, Release);
                let _ = init_tx.try_send(Err(error.clone()));
                control_state.status.store(4, Release);
                control_errors
                    .lock()
                    .unwrap()
                    .push_back((control_state.token.load(Relaxed), error));
            }
        });
        let initialized = init_rx.recv().map_err(|e| e.to_string())?;
        let (rate, channels) = match initialized {
            Ok(v) => v,
            Err(e) => {
                let _ = handle.join();
                return Err(e);
            }
        };
        Ok(Self {
            state,
            jobs: jobs_tx,
            prefetch: pre_tx,
            errors,
            thread: Some(handle),
            rate,
            channels,
            last_complete: 0,
            clock,
        })
    }

    fn play_source(&self, token: u64, source: Source, start: f64) -> Result<()> {
        if self.state.quit.load(Acquire) {
            return Err("Engine closed".into());
        }
        let generation = self.state.generation.fetch_add(1, AcqRel) + 1;
        self.state.token.store(token, Release);
        self.state.status.store(1, Release);
        self.state
            .position
            .store((start * self.rate as f64).round() as u64, Relaxed);
        self.state
            .command_ns
            .store(self.clock.elapsed().as_nanos() as u64, Relaxed);
        self.state.ready_ns.store(0, Relaxed);
        self.state.out_ns.store(0, Relaxed);
        self.jobs
            .try_send(Job {
                generation,
                token,
                source,
                start,
                prefetch: false,
            })
            .map_err(|_| "Decoder queue busy; retry audition".into())
    }
    pub fn play(&self, token: u64, path: PathBuf, start: f64) -> Result<()> {
        self.play_source(token, Source::Path(path), start)
    }
    /// PCM bridge is already device-rate stereo, copied once per audition.
    pub fn play_pcm(&self, token: u64, pcm: Vec<Frame>, start: f64) -> Result<()> {
        self.play_source(token, Source::Pcm(Arc::new(pcm)), start)
    }
    pub fn prefetch(&self, paths: Vec<PathBuf>) {
        let generation = self.state.prefetch_generation.fetch_add(1, AcqRel) + 1;
        for path in paths.into_iter().take(16) {
            let _ = self.prefetch.try_send(Job {
                generation,
                token: 0,
                source: Source::Path(path),
                start: 0.0,
                prefetch: true,
            });
        }
    }
    pub fn pause(&self) {
        self.state.generation.fetch_add(1, AcqRel);
        self.state.status.store(3, Release);
    }
    pub fn snapshot(&self) -> Snapshot {
        Snapshot {
            now_ns: self.clock.elapsed().as_nanos() as u64,
            token: self.state.token.load(Acquire),
            position: self.state.position.load(Relaxed),
            status: self.state.status.load(Acquire),
            peak: f32::from_bits(self.state.peak.load(Relaxed)),
            rms: f32::from_bits(self.state.rms.load(Relaxed)),
            xruns: self.state.xruns.load(Relaxed),
            starved: self.state.starved.load(Relaxed),
            command_ns: self.state.command_ns.load(Relaxed),
            ready_ns: self.state.ready_ns.load(Relaxed),
            out_ns: self.state.out_ns.load(Relaxed),
        }
    }
    pub fn drain_events(&mut self) -> Vec<(String, u64, String)> {
        let mut events = Vec::new();
        let completed = self.state.complete.load(Acquire);
        if completed != 0 && completed != self.last_complete {
            self.last_complete = completed;
            events.push(("complete".into(), completed, String::new()));
        }
        let mut errors = self.errors.lock().unwrap();
        for (token, error) in errors.drain(..) {
            events.push(("error".into(), token, error));
        }
        events
    }
    pub fn close(&mut self) {
        self.state.generation.fetch_add(1, AcqRel);
        self.state.quit.store(true, Release);
        if let Some(handle) = self.thread.take() {
            let _ = handle.join();
        }
    }
}
impl Drop for Engine {
    fn drop(&mut self) {
        self.close();
    }
}

fn open_stream<T: cpal::SizedSample + cpal::FromSample<f32>>(
    device: &cpal::Device,
    config: &cpal::StreamConfig,
    mut callback: Callback,
) -> Result<cpal::Stream> {
    let channels = config.channels as usize;
    let errors = callback.state.clone();
    let panic_state = callback.state.clone();
    device
        .build_output_stream(
            config,
            move |out: &mut [T], _| {
                // Unexpected panics silence the buffer; normal paths are allocation-free.
                if std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                    callback.render(out, channels)
                }))
                .is_err()
                {
                    out.fill(T::EQUILIBRIUM);
                    panic_state.status.store(4, Release);
                }
            },
            move |_| {
                errors.xruns.fetch_add(1, Relaxed);
                errors.status.store(4, Release);
            },
            None,
        )
        .map_err(|e| e.to_string())
}

#[allow(clippy::too_many_arguments)]
fn worker(
    jobs: Receiver<Job>,
    prefetch: Receiver<Job>,
    ready: Sender<Voice>,
    state: Arc<State>,
    errors: Arc<Mutex<VecDeque<(u64, String)>>>,
    cache: Arc<Mutex<Cache>>,
    rate: u32,
    clock: Instant,
) {
    while !state.quit.load(Acquire) {
        let job = crossbeam_channel::select_biased! {
            recv(jobs) -> job => job.ok(), recv(prefetch) -> job => job.ok(),
            default(Duration::from_millis(10)) => None,
        };
        let Some(job) = job else {
            continue;
        };
        if stale(&job, &state) {
            continue;
        }
        let result = produce(&job, &ready, &state, &cache, rate, clock);
        if let Err(error) = result {
            if !job.prefetch && job.generation == state.generation.load(Acquire) {
                state.status.store(4, Release);
                let mut errors = errors.lock().unwrap();
                if errors.len() == 64 {
                    errors.pop_front();
                }
                errors.push_back((job.token, error));
            }
        }
    }
}

fn send_voice(ready: &Sender<Voice>, mut voice: Voice, state: &State) -> Result<()> {
    // Shutdown must never join a producer blocked on a full ready queue.
    loop {
        if state.quit.load(Acquire) || voice.generation != state.generation.load(Acquire) {
            return Ok(());
        }
        match ready.send_timeout(voice, Duration::from_millis(2)) {
            Ok(()) => return Ok(()),
            Err(crossbeam_channel::SendTimeoutError::Timeout(value)) => voice = value,
            Err(_) => return Err("Engine control closed".into()),
        }
    }
}

fn stale(job: &Job, state: &State) -> bool {
    state.quit.load(Acquire)
        || job.generation
            != if job.prefetch {
                state.prefetch_generation.load(Acquire)
            } else {
                state.generation.load(Acquire)
            }
}

fn produce(
    job: &Job,
    ready: &Sender<Voice>,
    state: &State,
    cache: &Mutex<Cache>,
    rate: u32,
    clock: Instant,
) -> Result<()> {
    let identity = match &job.source {
        Source::Path(p) => key(p),
        _ => None,
    };
    let cached = if job.start == 0.0 {
        identity
            .as_ref()
            .and_then(|key| cache.lock().unwrap().get(key))
    } else {
        None
    };
    if job.prefetch && cached.is_some() {
        return Ok(());
    }
    let (mut producer, consumer) = RingBuffer::<Frame>::new(rate as usize / 2);
    let done = Arc::new(AtomicBool::new(false));
    let mut voice = Some(Voice {
        generation: job.generation,
        token: job.token,
        cursor: (job.start * rate as f64) as u64,
        gain: 0.0,
        frames: consumer,
        done: done.clone(),
    });
    let mut head = Vec::new();
    let mut cached_skip = 0;
    let mut cancelled = false;
    let mut write = |frames: &[Frame]| -> Result<bool> {
        for frame in frames {
            if stale(job, state) {
                cancelled = true;
                return Ok(false);
            }
            if head.len() < rate as usize / 2 {
                head.push(*frame);
            }
            if job.prefetch {
                if head.len() >= rate as usize / 2 {
                    return Ok(false);
                }
                continue;
            }
            loop {
                if producer.push(*frame).is_ok() {
                    break;
                }
                if state.quit.load(Acquire) || job.generation != state.generation.load(Acquire) {
                    cancelled = true;
                    return Ok(false);
                }
                thread::sleep(Duration::from_millis(1));
            }
            // Publish a small primed head, then let the reader keep ahead.
            if producer.slots() <= rate as usize / 2 - 512 {
                if let Some(voice) = voice.take() {
                    state
                        .ready_ns
                        .store(clock.elapsed().as_nanos() as u64, Relaxed);
                    send_voice(ready, voice, state)?;
                }
            }
        }
        Ok(true)
    };
    if let Some((frames, complete)) = &cached {
        if !write(frames)? {
            done.store(true, Release);
            return Ok(());
        }
        cached_skip = frames.len();
        if *complete {
            if let Some(voice) = voice.take() {
                send_voice(ready, voice, state)?;
            }
            done.store(true, Release);
            return Ok(());
        }
    }
    let result = match &job.source {
        Source::Path(path) => decoder::stream(path, job.start, rate, |frames| {
            let skip = cached_skip.min(frames.len());
            cached_skip -= skip;
            write(&frames[skip..])
        }),
        Source::Pcm(frames) => {
            let start = ((job.start * rate as f64) as usize).min(frames.len());
            write(&frames[start..]).map(|_| ())
        }
    };
    if !cancelled && result.is_ok() && !state.quit.load(Acquire) {
        if let Some(voice) = voice.take() {
            state
                .ready_ns
                .store(clock.elapsed().as_nanos() as u64, Relaxed);
            send_voice(ready, voice, state)?;
        }
        if job.start == 0.0 && cached.is_none() {
            if let (Some(identity), Source::Path(path)) = (identity, &job.source) {
                if key(path).as_ref() == Some(&identity) {
                    let complete = !job.prefetch || head.len() < rate as usize / 2;
                    // Only a head is cached for long sources; completion means all
                    // decoded output fit in the head, never merely that decode ended.
                    let complete = complete
                        && probe(path)
                            .map(|(r, n, _)| n > 0 && n as f64 / r as f64 <= 0.5)
                            .unwrap_or(false);
                    cache.lock().unwrap().insert(identity, head, complete);
                }
            }
        }
    }
    done.store(true, Release);
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    #[global_allocator]
    static A: assert_no_alloc::AllocDisabler = assert_no_alloc::AllocDisabler;

    #[test]
    fn callback_does_not_allocate_and_completes() {
        let state = Arc::new(State::default());
        state.generation.store(1, Release);
        let (mut tx, rx) = RingBuffer::new(8);
        let (retired, mut retired_rx) = RingBuffer::new(32);
        let (mut producer, frames) = RingBuffer::new(1024);
        for _ in 0..512 {
            producer.push([0.5, -0.5]).unwrap();
        }
        tx.push(Voice {
            generation: 1,
            token: 7,
            cursor: 0,
            gain: 0.0,
            frames,
            done: Arc::new(AtomicBool::new(true)),
        })
        .ok()
        .unwrap();
        let mut cb = Callback {
            incoming: rx,
            retired,
            voices: [None, None],
            state: state.clone(),
            fade_step: 0.01,
            clock: Instant::now(),
        };
        let mut out = [0.0f32; 2048];
        assert_no_alloc::assert_no_alloc(|| cb.render(&mut out, 2));
        assert_eq!(state.complete.load(Acquire), 7);
        assert!(out[300] > 0.0);
        assert!(retired_rx.pop().is_ok());
    }

    #[test]
    fn decoder_resamples_and_seeks_with_bounded_packets() {
        let path = std::env::temp_dir().join(format!(
            "sm-engine-{}.wav",
            Instant::now().elapsed().as_nanos()
        ));
        let spec = hound::WavSpec {
            channels: 1,
            sample_rate: 8000,
            bits_per_sample: 16,
            sample_format: hound::SampleFormat::Int,
        };
        let mut writer = hound::WavWriter::create(&path, spec).unwrap();
        for i in 0..8000 {
            writer
                .write_sample((i as f32 / 8000.0 * 16000.0) as i16)
                .unwrap();
        }
        writer.finalize().unwrap();
        let mut frames = Vec::new();
        decoder::stream(&path, 0.25, 48000, |chunk| {
            frames.extend_from_slice(chunk);
            Ok(true)
        })
        .unwrap();
        assert_eq!(frames.len(), 36000);
        assert!((frames[18000][0] - 0.625 * 16000.0 / 32768.0).abs() < 0.01);
        std::fs::remove_file(path).unwrap();
    }

    #[test]
    fn replacement_and_full_ready_queue_can_shutdown() {
        let mut engine = Engine::new(None, 256, 16, true).unwrap();
        for token in 1..40 {
            let _ = engine.play_pcm(token, vec![[0.5, 0.5]; 48000], 0.0);
        }
        engine.close();
    }

    #[test]
    fn null_backend_pcm_pause_close() {
        let mut engine = Engine::new(None, 256, 16, true).unwrap();
        engine.play_pcm(1, vec![[0.5, 0.5]; 48000], 0.0).unwrap();
        let deadline = Instant::now() + Duration::from_secs(2);
        while engine.snapshot().position == 0 {
            assert!(Instant::now() < deadline);
            thread::sleep(Duration::from_millis(2));
        }
        engine.pause();
        assert_eq!(engine.snapshot().status, 3);
        engine.close();
        assert!(engine.play_pcm(2, vec![[0.0, 0.0]], 0.0).is_err());
    }
}
