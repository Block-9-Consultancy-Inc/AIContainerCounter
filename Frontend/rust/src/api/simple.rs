use parking_lot::RwLock;
use lazy_static::lazy_static;
use rust_socketio::{
    asynchronous::{Client, ClientBuilder},
    Payload,
};
use crate::frb_generated::StreamSink;
use log::warn;
use serde_json::json;
use futures_util::FutureExt;  

lazy_static! {
    static ref DETECTION_EVENT_STREAM_SINK: RwLock<Option<StreamSink<String>>> =
        RwLock::new(None);
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
                },
                Payload::Binary(bin_data) => {
                    println!("Received bytes: {:#?}", bin_data);
                    if let Some(sink) = &*DETECTION_EVENT_STREAM_SINK.read() {
                        let _ = sink.add(format!("Received bytes: {:#?}", bin_data));
                    }
                },
                // Use Payload::Text instead
                #[allow(deprecated)]
                Payload::String(str) => {
                    println!("Received: {}", str);
                    if let Some(sink) = &*DETECTION_EVENT_STREAM_SINK.read() {
                        let _ = sink.add(format!("Received: {}", str));
                    }
                },
            }
            socket
                .emit("test", json!({"got ack": true}))
                .await
                .expect("Server unreachable");
        }
        .boxed()
    };

    // get a socket that is connected to the admin namespace
    let socket = ClientBuilder::new("http://localhost:5000/")
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
        .expect("Connection failed");

    println!("connected (manual)");

    let _ = socket.emit("test", "test rust").await;

    println!("emitted test (manual)");
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
