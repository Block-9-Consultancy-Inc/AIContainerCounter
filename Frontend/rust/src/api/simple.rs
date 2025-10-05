use std::{thread, time};

use crate::frb_generated::StreamSink;
use futures_util::FutureExt;
use lazy_static::lazy_static;
use log::warn;
use parking_lot::RwLock;
use rust_socketio::{
    asynchronous::{Client, ClientBuilder},
    Payload,
};
use serde_json::json;

lazy_static! {
    static ref DETECTION_EVENT_STREAM_SINK: RwLock<Option<StreamSink<String>>> = RwLock::new(None);
}

lazy_static! {
    static ref SOCKET: RwLock<Option<Client>> = RwLock::new(None);
}

pub fn set_detection_event_stream_sink(stream_sink: StreamSink<String>) {
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

#[tokio::main]
pub async fn connect_to_socket_server() {
    let callback = |payload: Payload, socket: Client| {
        async move {
            match payload {
                Payload::Text(values) => {
                    println!("Received: {:#?}", values);
                    if let Some(sink) = &*DETECTION_EVENT_STREAM_SINK.read() {
                        let _ = sink.add(format!("Received: {:#?}", values));
                    }
                }
                Payload::Binary(bin_data) => {
                    println!("Received bytes: {:#?}", bin_data);
                    if let Some(sink) = &*DETECTION_EVENT_STREAM_SINK.read() {
                        let _ = sink.add(format!("Received bytes: {:#?}", bin_data));
                    }
                }
                // Use Payload::Text instead
                #[allow(deprecated)]
                Payload::String(str) => {
                    println!("Received: {}", str);
                    if let Some(sink) = &*DETECTION_EVENT_STREAM_SINK.read() {
                        let _ = sink.add(format!("Received: {}", str));
                    }
                }
            }
            socket
                .emit("test", json!({"got ack": true}))
                .await
                .expect("Server unreachable");
        }
        .boxed()
    };

    let mut guard = SOCKET.write();
    let overriding = guard.is_some();

    *guard = Some(
        ClientBuilder::new("http://localhost:5000/")
            .transport_type(rust_socketio::TransportType::Websocket)
            .on("test", callback)
            .on("detection_event", callback)
            .on("connect", |msg, _| {
                async move { println!("Connected: {:#?}", msg) }.boxed()
            })
            .on("error", |err, _| {
                async move { eprintln!("Error: {:#?}", err) }.boxed()
            })
            .connect()
            .await
            .expect("Connection failed"),
    );

    drop(guard);

    if overriding {
        warn!(
            "SOCKET created but already exists, thus overriding. \
            (This may or may not be a problem. It will happen normally if hot-reload Flutter app.)"
        );
    }

    println!("connected (manual)");


    loop {
        if let Some(socket) = &*SOCKET.read() {
            let _ = socket.emit("test", "test rust").await;
        }
        println!("emitted test (manual in loop)");
        thread::sleep(time::Duration::from_secs(5));
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
