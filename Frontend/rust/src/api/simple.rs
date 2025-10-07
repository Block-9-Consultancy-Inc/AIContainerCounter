use crate::frb_generated::StreamSink;
use lazy_static::lazy_static;
use log::warn;
use parking_lot::RwLock;
use rust_socketio::{client::Client, ClientBuilder, Payload};
use base64::{engine::general_purpose::STANDARD, Engine};



#[flutter_rust_bridge::frb(opaque)]
pub struct Socket {
    inner: Option<Client>,
}

pub struct FramePayload {
    pub frame: Vec<u8>,
    pub total_in: i64,
    pub total_out: i64
}

lazy_static! {
    static ref EVENT_STREAM_SINK: RwLock<Option<StreamSink<String>>> = RwLock::new(None);
}

lazy_static! {
    static ref DETECTION_EVENT_STREAM_SINK: RwLock<Option<StreamSink<FramePayload>>> = RwLock::new(None);
}


pub fn set_event_stream_sink(stream_sink: StreamSink<String>) {
    let mut guard = EVENT_STREAM_SINK.write();
    let overriding = guard.is_some();

    *guard = Some(stream_sink);

    drop(guard);

    if overriding {
        warn!(
            "SendToDartLogger::set_stream_sink but already exist a sink, thus overriding. \
            (This may or may not be a problem. It will happen normally if hot-reload Flutter app.)"
        );
    }
}

pub fn set_detection_event_stream_sink(stream_sink: StreamSink<FramePayload>) {
    let mut guard = DETECTION_EVENT_STREAM_SINK.write();
    let overriding = guard.is_some();

    *guard = Some(stream_sink);

    drop(guard);

    if overriding {
        warn!(
            "SendToDartLogger::set_stream_sink but already exist a sink, thus overriding. \
            (This may or may not be a problem. It will happen normally if hot-reload Flutter app.)"
        );
    }
}



#[flutter_rust_bridge::frb(sync)]
pub fn new_socket() -> Socket { Socket { inner: None } }

impl Socket {
    pub fn emit_event(&mut self, event: String, data: String) -> bool {
        if self.inner.is_none() {
            eprintln!("socket has not been initialized yet!");
            return false;
        }

        let res = self.inner.as_ref().unwrap().emit(event, data);
        return res.is_ok();
    }

    pub fn connect_to_socket_server(&mut self, server_address: String) -> bool {
        if self.inner.is_some() {
            println!("socket already initialized, cancelling");
            return true;
        }

        let callback = |payload: Payload, _| {
            match payload {
                Payload::Text(values) => {
                    println!("Received values: {:#?}", values);
                    let object = values[0].as_object().unwrap();
                    let encoded_frame_base64 = object.get("encoded_frame").unwrap().as_str().unwrap();
                    let frame = STANDARD.decode(encoded_frame_base64).unwrap();
                    let frame_payload = FramePayload { 
                        frame,
                        total_in: object.get("total_in").unwrap().as_i64().unwrap(),
                        total_out: object.get("total_out").unwrap().as_i64().unwrap()
                    };
                    if let Some(sink) = &*DETECTION_EVENT_STREAM_SINK.read() {
                        let _ = sink.add(frame_payload);
                    }
                }
                Payload::Binary(bin_data) => {
                    println!("Received bytes: {:#?}", bin_data);
                    if let Some(sink) = &*EVENT_STREAM_SINK.read() {
                        let _ = sink.add(format!("Received bytes: {:#?}", bin_data));
                    }
                }
                // Use Payload::Text instead
                #[allow(deprecated)]
                Payload::String(str) => {
                    println!("Received: {}", str);
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
            .on("connect", |msg, _| {
                println!("Connected: {:#?}", msg)
            })
            .on("error", |err, _| {
                eprintln!("Error: {:#?}", err)
            })
            .connect();

            
        if client.is_ok() {
            self.inner = Some(client.unwrap());
            return true;
        }

        return false;
    }
}

#[flutter_rust_bridge::frb(sync)] // Synchronous mode for simplicity of the demo
pub fn greet(name: String) -> String {
    println!("Hello Rust");
    format!("Hello, {name}!")
}

#[flutter_rust_bridge::frb(init)]
pub fn init_app() {
    // Default utilities - feel free to customize
    flutter_rust_bridge::setup_default_user_utils();
}
