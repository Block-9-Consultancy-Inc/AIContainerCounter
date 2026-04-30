#[derive(Clone)]
pub struct RawImage {
    pub format: RawImageFormat,
    pub data: Vec<u8>,
    pub width: usize,
    pub height: usize,
}

impl RawImage {
    pub(crate) fn new_from_rgba_data(data: Vec<u8>, width: usize, height: usize) -> RawImage {
        Self {
            format: RawImageFormat::Rgba,
            data,
            width,
            height,
        }
    }
}

#[derive(Clone)]
pub enum RawImageFormat {
    Rgba,
}
