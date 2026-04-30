
use crate::api::models::images::RawImage;

pub fn decode_jpeg_to_rgba(jpeg_data: &[u8]) -> RawImage {
    let image = turbojpeg::decompress(jpeg_data, turbojpeg::PixelFormat::RGBA).unwrap();

    RawImage::new_from_rgba_data(
        image.pixels,
        image.width,
        image.height,
    )
}
