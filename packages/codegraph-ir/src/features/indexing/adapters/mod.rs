#[cfg(feature = "python")]
pub mod projection;
#[cfg(feature = "python")]
pub mod projection_dict; // Dict-based API workaround
#[cfg(feature = "python")]
pub mod py_writer; // SOTA: PyPayloadWriter for Python
