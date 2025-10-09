use std::ffi::{c_int, c_void};

use dlopen::{symbor::{Library, Symbol}, Error as LibError};

use crate::models::images::RawImage;

use log::error;

use std::time::Instant;


lazy_static::lazy_static! {
    pub static ref TEXTURE_RGBA_RENDERER_PLUGIN: Result<Library, LibError> = Library::open("libtexture_rgba_renderer_plugin.so");
}

pub type FlutterRgbaRendererPluginOnRgba = unsafe extern "C" fn(
    texture_rgba: *mut c_void,
    buffer: *const u8,
    len: c_int,
    width: c_int,
    height: c_int,
    dst_rgba_stride: c_int,
);

#[derive(Clone)]
pub struct FlutterTexture {
    ptr: usize, // TextureRgba pointer in flutter native.
    on_rgba_func: Option<Symbol<'static, FlutterRgbaRendererPluginOnRgba>>,
}

impl FlutterTexture {
    pub fn new(ptr: usize) -> Self {
        let on_rgba_func = match &*TEXTURE_RGBA_RENDERER_PLUGIN {
            Ok(lib) => {
                let find_sym_res = unsafe {
                    lib.symbol::<FlutterRgbaRendererPluginOnRgba>("FlutterRgbaRendererPluginOnRgba")
                };
                match find_sym_res {
                    Ok(sym) => Some(sym),
                    Err(error) => {
                        error!("Failed to find symbol FlutterRgbaRendererPluginOnRgba: {:#?}", error);
                        None
                    }
                }
            }
            Err(error) => {
                error!("Failed to load texture rgba renderer plugin: {:#?}", error);
                None
            }
        };
        Self {
            ptr,
            on_rgba_func,
        }
    }
}

impl FlutterTexture {
    pub fn on_rgba(&self, raw_image: &RawImage) {
        if self.ptr == usize::default() {
            return;
        }

        if let Some(func) = &self.on_rgba_func {
            println!("starting frame");
            let now = Instant::now();
            unsafe {
                func(
                    self.ptr as _,
                    raw_image.data.as_ptr() as _,
                    raw_image.data.len() as _,
                    raw_image.width as _,
                    raw_image.height as _,
                    0,
                )
            };
            let time = now.elapsed();
            println!("took {:#?} ms", time.as_millis());
        }
    }
}
