//! Thin stable-ABI bindings; Python never participates in the device callback.
use pyo3::{
    exceptions::PyRuntimeError,
    prelude::*,
    types::{PyBytes, PyDict},
};
use std::path::PathBuf;

fn error(message: String) -> PyErr {
    PyRuntimeError::new_err(message)
}

#[pyclass]
struct Engine {
    inner: sm_engine::Engine,
}

#[pymethods]
impl Engine {
    #[new]
    #[pyo3(signature = (device=None, buffer_frames=1024, cache_mb=64, backend="device"))]
    fn new(
        py: Python<'_>,
        device: Option<usize>,
        buffer_frames: u32,
        cache_mb: usize,
        backend: &str,
    ) -> PyResult<Self> {
        if ![128, 256, 512, 1024, 2048].contains(&buffer_frames) || !(16..=2048).contains(&cache_mb)
        {
            return Err(error("Invalid buffer/cache size".into()));
        }
        if !["device", "null"].contains(&backend) {
            return Err(error("Unknown backend".into()));
        }
        let null = backend == "null";
        py.detach(|| sm_engine::Engine::new(device, buffer_frames, cache_mb, null))
            .map(|inner| Self { inner })
            .map_err(error)
    }
    fn play(&self, py: Python<'_>, token: u64, path: String, start_s: f64) -> PyResult<()> {
        py.detach(|| {
            self.inner
                .play(token, PathBuf::from(path), start_s.max(0.0))
        })
        .map_err(error)
    }
    fn play_pcm(
        &self,
        py: Python<'_>,
        token: u64,
        data: &Bound<'_, PyBytes>,
        start_s: f64,
    ) -> PyResult<()> {
        // One owned copy per audition; never a Python/FFI call per audio buffer.
        let bytes = data.as_bytes().to_vec();
        if bytes.len() % 8 != 0 {
            return Err(error(
                "PCM must be interleaved little-endian stereo float32".into(),
            ));
        }
        py.detach(|| {
            // Length was checked above: every chunk is one complete stereo frame.
            let frames = bytes
                .as_chunks::<8>()
                .0
                .iter()
                .map(|b| {
                    [
                        f32::from_le_bytes(b[..4].try_into().unwrap()),
                        f32::from_le_bytes(b[4..].try_into().unwrap()),
                    ]
                })
                .collect();
            self.inner.play_pcm(token, frames, start_s.max(0.0))
        })
        .map_err(error)
    }
    fn prefetch(&self, py: Python<'_>, paths: Vec<String>) {
        py.detach(|| {
            self.inner
                .prefetch(paths.into_iter().map(PathBuf::from).collect())
        });
    }
    fn pause(&self, py: Python<'_>) {
        py.detach(|| self.inner.pause());
    }
    fn snapshot<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let state = self.inner.snapshot();
        let result = PyDict::new(py);
        result.set_item("now_ns", state.now_ns)?;
        result.set_item("token", state.token)?;
        result.set_item("position_frames", state.position)?;
        result.set_item("status", state.status)?;
        result.set_item("peak", state.peak)?;
        result.set_item("rms", state.rms)?;
        result.set_item("xruns", state.xruns)?;
        result.set_item("starved", state.starved)?;
        result.set_item("command_ns", state.command_ns)?;
        result.set_item("ready_ns", state.ready_ns)?;
        result.set_item("out_ns", state.out_ns)?;
        result.set_item("sample_rate", self.inner.rate)?;
        result.set_item("channels", self.inner.channels)?;
        Ok(result)
    }
    fn drain_events(&mut self) -> Vec<(String, u64, String)> {
        self.inner.drain_events()
    }
    fn close(&mut self, py: Python<'_>) {
        py.detach(|| self.inner.close());
    }
}

#[pyfunction]
fn probe(py: Python<'_>, path: String) -> PyResult<(u32, u64, usize)> {
    py.detach(|| sm_engine::probe(&PathBuf::from(path)))
        .map_err(error)
}

#[pyfunction]
fn devices(py: Python<'_>) -> PyResult<Vec<String>> {
    py.detach(sm_engine::Engine::devices).map_err(error)
}

#[pymodule]
fn _engine(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<Engine>()?;
    module.add_function(wrap_pyfunction!(devices, module)?)?;
    module.add_function(wrap_pyfunction!(probe, module)?)?;
    Ok(())
}
