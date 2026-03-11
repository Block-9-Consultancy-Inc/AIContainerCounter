use crate::{
    frb_generated::StreamSink,
    utils::{flutter_texture::FlutterTexture, jpeg::decode_jpeg_to_rgba},
};
use base64::{engine::general_purpose::STANDARD, Engine};
use flutter_rust_bridge::frb;
use lazy_static::lazy_static;
use log::warn;
use parking_lot::RwLock;
use rust_socketio::{client::Client, ClientBuilder, Event, Payload};
use serde_json::json;
use std::{collections::HashMap, time::Instant};
use crate::models::count::{Count, BatchGlobalState};

#[frb(opaque)]
pub struct Socket {
    inner: Option<Client>,
}

lazy_static! {
    static ref CURRENT_FLUTTER_TEXTURE: RwLock<Option<FlutterTexture>> = RwLock::new(None);
}

lazy_static! {
    static ref EVENT_STREAM_SINK: RwLock<Option<StreamSink<String>>> = RwLock::new(None);
}

lazy_static! {
    static ref GLOBAL_STATE_STREAM_SINK: RwLock<Option<StreamSink<BatchGlobalState>>> =
        RwLock::new(None);
}

lazy_static! {
    static ref PREVIOUS_BATCH_GLOBAL_STATE: RwLock<Option<BatchGlobalState>> = RwLock::new(None);
}

lazy_static! {
    static ref DETECTION_EVENT_STREAM_SINK: RwLock<Option<StreamSink<Count>>> = RwLock::new(None);
}

pub fn set_prev_batch_global_state(new_batch_global_state: BatchGlobalState) {
    let mut guard = PREVIOUS_BATCH_GLOBAL_STATE.write();
    *guard = Some(new_batch_global_state);
    drop(guard);
}

pub fn set_event_stream_sink(stream_sink: StreamSink<String>) {
    let mut guard = EVENT_STREAM_SINK.write();
    let overriding = guard.is_some();

    *guard = Some(stream_sink);

    drop(guard);

    if overriding {
        warn!(
            "EVENT_STREAM_SINK but already exist a sink, thus overriding. \
            (This may or may not be a problem. It will happen normally if hot-reload Flutter app.)"
        );
    }
}

pub fn set_json_response_stream_sink(stream_sink: StreamSink<BatchGlobalState>) {
    let mut guard = GLOBAL_STATE_STREAM_SINK.write();
    let overriding = guard.is_some();

    *guard = Some(stream_sink);

    drop(guard);

    if overriding {
        warn!(
            "JSON_RESPONSE_STREAM_SINK but already exist a sink, thus overriding. \
            (This may or may not be a problem. It will happen normally if hot-reload Flutter app.)"
        );
    }
}

pub fn set_detection_event_stream_sink(stream_sink: StreamSink<Count>) {
    let mut guard = DETECTION_EVENT_STREAM_SINK.write();
    let overriding = guard.is_some();

    *guard = Some(stream_sink);

    drop(guard);

    if overriding {
        warn!(
            "DETECTION_EVENT_STREAM_SINK but already exist a sink, thus overriding. \
            (This may or may not be a problem. It will happen normally if hot-reload Flutter app.)"
        );
    }
}

pub fn initialize_flutter_texture(texture_ptr: usize) {
    let mut guard = CURRENT_FLUTTER_TEXTURE.write();
    let overriding = guard.is_some();

    println!("got texture ptr {:#?}", texture_ptr);
    *guard = Some(FlutterTexture::new(texture_ptr));

    drop(guard);

    if overriding {
        warn!(
            "CURRENT_FLUTTER_TEXTURE but already exist a sink, thus overriding. \
            (This may or may not be a problem. It will happen normally if hot-reload Flutter app.)"
        );
    }
}

#[frb(sync)]
pub fn new_socket() -> Socket {
    Socket { inner: None }
}

impl Socket {
    pub fn emit_event(&mut self, event: String, data: String) -> bool {
        if self.inner.is_none() {
            eprintln!("socket has not been initialized yet!");
            return false;
        }

        let res = self.inner.as_ref().unwrap().emit(event, data);
        return res.is_ok();
    }

    pub fn emit_new_expected_category_count(&mut self, data: HashMap<String, u64>) -> bool {
        if self.inner.is_none() {
            eprintln!("socket has not been initialized yet!");
            return false;
        }

        let mut map_data = serde_json::Map::new();
        for (key, value) in data.iter() {
            map_data.insert(key.to_owned(), json!(value.to_owned()));
        }
        let res = self
            .inner
            .as_ref()
            .unwrap()
            .emit("set-expected-count", serde_json::Value::Object(map_data));
        return res.is_ok();
    }

    pub fn connect_to_socket_server(&mut self, server_address: String) -> bool {
        if self.inner.is_some() {
            println!("socket already initialized, cancelling");
            return true;
        }

        let callback = move |payload: Payload, _| {
            match payload {
                Payload::Text(values) => {
                    // println!("Received values: {:#?}", values);
                    let object = &values[0];
                    let frame_payload = Count::from_json(object);
                    if let Some(sink) = &*DETECTION_EVENT_STREAM_SINK.read() {
                        let _ = sink.add(frame_payload);
                    }
                    let encoded_frame = object.get("encoded_frame");
                    if encoded_frame.is_some() {
                        let mut now = Instant::now();
                        let encoded_frame_base64 = encoded_frame.unwrap().as_str().unwrap();
                        let frame = STANDARD.decode(encoded_frame_base64).unwrap();
                        let base64_decode_time = now.elapsed();
                        println!(
                            "base64_decode took {:#?} ms",
                            base64_decode_time.as_millis()
                        );
                        now = Instant::now();
                        let raw_frame = decode_jpeg_to_rgba(frame.as_slice());
                        let jpeg_to_rgba_decode_time = now.elapsed();
                        println!(
                            "jpeg_to_rgba took {:#?} ms",
                            jpeg_to_rgba_decode_time.as_millis()
                        );
                        if let Some(renderer) = &*CURRENT_FLUTTER_TEXTURE.read() {
                            renderer.on_rgba(&raw_frame);
                        }
                    }
                }
                Payload::Binary(bin_data) => {
                    // println!("Received bytes: {:#?}", bin_data);
                    if let Some(sink) = &*EVENT_STREAM_SINK.read() {
                        let _ = sink.add(format!("Received bytes: {:#?}", bin_data));
                    }
                }
                // Use Payload::Text instead
                #[allow(deprecated)]
                Payload::String(str) => {
                    // println!("Received: {}", str);
                    if let Some(sink) = &*EVENT_STREAM_SINK.read() {
                        let _ = sink.add(format!("Received: {}", str));
                    }
                }
            }
        };

        let client = ClientBuilder::new(&server_address)
            .transport_type(rust_socketio::TransportType::Websocket)
            .on("test", callback)
            .on("detection_event", callback)
            .on("connect", |msg, _| println!("Connected: {:#?}", msg))
            .on_any(|event: Event, payload: Payload, _| {
                if !event.as_str().contains("state") {
                    return;
                }

                let payload_json = match payload {
                    Payload::Text(values) => Some(values[0].clone()),
                    _ => None,
                };

                if payload_json.is_none() {
                    return;
                }

                if let Some(sink) = &*GLOBAL_STATE_STREAM_SINK.read() {
                    let mut new_batch_global_state = BatchGlobalState::new(payload_json.unwrap());
                    let prev_batch_global_state = PREVIOUS_BATCH_GLOBAL_STATE.read();
                    if prev_batch_global_state.is_some() {
                        new_batch_global_state.merge((*prev_batch_global_state).as_ref().unwrap());
                    }
                    let _ = sink.add(new_batch_global_state.clone());
                    drop(prev_batch_global_state);
                    set_prev_batch_global_state(new_batch_global_state);
                }
            })
            .on("error", |err, _| eprintln!("Error: {:#?}", err))
            .connect();

        if client.is_ok() {
            self.inner = Some(client.unwrap());
            return true;
        }

        return false;
    }
}

#[frb(sync)] // Synchronous mode for simplicity of the demo
pub fn greet(name: String) -> String {
    println!("Hello Rust");
    format!("Hello, {name}!")
}

#[frb(init)]
pub fn init_app() {
    // Default utilities - feel free to customize
    flutter_rust_bridge::setup_default_user_utils();
}
