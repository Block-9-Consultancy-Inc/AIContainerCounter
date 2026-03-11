use crate::{
    frb_generated::StreamSink,
    utils::{flutter_texture::FlutterTexture, jpeg::decode_jpeg_to_rgba},
};
use base64::{engine::general_purpose::STANDARD, Engine};
use chrono::{DateTime, Local, NaiveDateTime, TimeZone};
use flutter_rust_bridge::frb;
use lazy_static::lazy_static;
use log::warn;
use parking_lot::RwLock;
use rust_socketio::{client::Client, ClientBuilder, Event, Payload};
use serde_json::{json, Value};
use std::{collections::HashMap, str::FromStr, time::Instant};

#[frb(opaque)]
pub struct Socket {
    inner: Option<Client>,
}

pub struct Count {
    pub count: u64,
    pub can_count: u64,
    pub plastic_count: u64,
    pub drinkbox_count: u64,
    pub gabletop_count: u64,
    pub pouch_count: u64,
    pub expected_count: Option<u64>,
    pub expected_can_count: Option<u64>,
    pub expected_plastic_count: Option<u64>,
    pub expected_drinkbox_count: Option<u64>,
    pub expected_gabletop_count: Option<u64>,
    pub expected_pouch_count: Option<u64>,
    pub count_accuracy: Option<f64>,
    pub can_accuracy: Option<f64>,
    pub plastic_accuracy: Option<f64>,
    pub drinkbox_accuracy: Option<f64>,
    pub gabletop_accuracy: Option<f64>,
    pub pouch_accuracy: Option<f64>,
}

impl Count {
    #[frb(sync)]
    pub fn new(
        count: u64,
        can_count: u64,
        plastic_count: u64,
        drinkbox_count: u64,
        gabletop_count: u64,
        pouch_count: u64,
        expected_can_count: Option<u64>,
        expected_plastic_count: Option<u64>,
        expected_drinkbox_count: Option<u64>,
        expected_gabletop_count: Option<u64>,
        expected_pouch_count: Option<u64>,
    ) -> Self {
        let expected_count = {
            if expected_can_count.is_none()
                || expected_plastic_count.is_none()
                || expected_drinkbox_count.is_none()
                || expected_gabletop_count.is_none()
                || expected_pouch_count.is_none()
            {
                None
            } else {
                Some(
                    expected_can_count.unwrap()
                        + expected_plastic_count.unwrap()
                        + expected_drinkbox_count.unwrap()
                        + expected_gabletop_count.unwrap()
                        + expected_pouch_count.unwrap(),
                )
            }
        };
        Self {
            count,
            can_count,
            plastic_count,
            drinkbox_count,
            gabletop_count,
            pouch_count,
            expected_count,
            expected_can_count,
            expected_plastic_count,
            expected_drinkbox_count,
            expected_gabletop_count,
            expected_pouch_count,
            count_accuracy: Self::compute_accuracy(count, expected_count),
            can_accuracy: Self::compute_accuracy(can_count, expected_can_count),
            plastic_accuracy: Self::compute_accuracy(plastic_count, expected_plastic_count),
            drinkbox_accuracy: Self::compute_accuracy(drinkbox_count, expected_drinkbox_count),
            gabletop_accuracy: Self::compute_accuracy(gabletop_count, expected_gabletop_count),
            pouch_accuracy: Self::compute_accuracy(pouch_count, expected_pouch_count),
        }
    }

    fn from_json(json_data: &Value) -> Self {
        Self::new(
            json_data.get("count").unwrap().as_u64().unwrap(),
            json_data.get("can_count").unwrap().as_u64().unwrap(),
            json_data.get("plastic_count").unwrap().as_u64().unwrap(),
            json_data.get("drinkbox_count").unwrap().as_u64().unwrap(),
            json_data.get("gabletop_count").unwrap().as_u64().unwrap(),
            json_data.get("pouch_count").unwrap().as_u64().unwrap(),
            json_data.get("expected_can_count").unwrap().as_u64(),
            json_data.get("expected_plastic_count").unwrap().as_u64(),
            json_data.get("expected_drinkbox_count").unwrap().as_u64(),
            json_data.get("expected_gabletop_count").unwrap().as_u64(),
            json_data.get("expected_pouch_count").unwrap().as_u64(),
        )
    }

    fn for_today_summary(json_data: &Value) -> Self {
        Self {
            count: json_data.get("count").unwrap().as_u64().unwrap(),
            can_count: json_data.get("can_count").unwrap().as_u64().unwrap(),
            plastic_count: json_data.get("plastic_count").unwrap().as_u64().unwrap(),
            drinkbox_count: json_data.get("drinkbox_count").unwrap().as_u64().unwrap(),
            gabletop_count: json_data.get("gabletop_count").unwrap().as_u64().unwrap(),
            pouch_count: json_data.get("pouch_count").unwrap().as_u64().unwrap(),
            expected_count: None,
            expected_can_count: None,
            expected_plastic_count: None,
            expected_drinkbox_count: None,
            expected_gabletop_count: None,
            expected_pouch_count: None,
            count_accuracy: json_data.get("count_accuracy").unwrap().as_f64(),
            can_accuracy: json_data.get("can_accuracy").unwrap().as_f64(),
            plastic_accuracy: json_data.get("plastic_accuracy").unwrap().as_f64(),
            drinkbox_accuracy: json_data.get("drinkbox_accuracy").unwrap().as_f64(),
            gabletop_accuracy: json_data.get("gabletop_accuracy").unwrap().as_f64(),
            pouch_accuracy: json_data.get("pouch_accuracy").unwrap().as_f64(),
        }
    }

    fn compute_accuracy(actual: u64, expected: Option<u64>) -> Option<f64> {
        if expected.is_none() {
            return None;
        }
        Some((1.0 - ((actual.abs_diff(expected.unwrap()) as f64) / (expected.unwrap() as f64))) * 100.0)
    }
}

impl Clone for Count {
    fn clone(&self) -> Self {
        Self {
            count: self.count,
            can_count: self.can_count,
            plastic_count: self.plastic_count,
            drinkbox_count: self.drinkbox_count,
            gabletop_count: self.gabletop_count,
            pouch_count: self.pouch_count,
            expected_count: self.expected_count,
            expected_can_count: self.expected_can_count,
            expected_plastic_count: self.expected_plastic_count,
            expected_drinkbox_count: self.expected_drinkbox_count,
            expected_gabletop_count: self.expected_gabletop_count,
            expected_pouch_count: self.expected_pouch_count,
            count_accuracy: self.count_accuracy,
            can_accuracy: self.can_accuracy,
            plastic_accuracy: self.plastic_accuracy,
            drinkbox_accuracy: self.drinkbox_accuracy,
            gabletop_accuracy: self.gabletop_accuracy,
            pouch_accuracy: self.pouch_accuracy,
        }
    }
}

pub struct TodaySummary {
    pub num_of_batches: u64,
    pub num_of_batches_with_expected: u64,
    pub count: Count,
}

pub struct Batch {
    pub id: String,
    pub area_collected: Option<String>,
    pub time_started: DateTime<Local>,
    pub time_submitted: DateTime<Local>,
    pub count: Count,
    pub yolo_model: String,
    pub category_model: String,
}

impl Clone for Batch {
    fn clone(&self) -> Self {
        Self {
            id: self.id.clone(),
            area_collected: self.area_collected.clone(),
            time_started: self.time_started,
            time_submitted: self.time_submitted,
            count: self.count.clone(),
            yolo_model: self.yolo_model.clone(),
            category_model: self.category_model.clone(),
        }
    }
}

impl Clone for TodaySummary {
    fn clone(&self) -> Self {
        Self {
            num_of_batches: self.num_of_batches,
            count: self.count.clone(),
            num_of_batches_with_expected: self.num_of_batches_with_expected,
        }
    }
}

pub struct BatchGlobalState {
    pub today_summary: TodaySummary,
    pub batches: Vec<Batch>,
}

impl BatchGlobalState {
    fn new(json_str_data: Value) -> Self {
        let string_data = json_str_data.as_str().unwrap();
        let json_data = serde_json::from_str::<Value>(string_data).unwrap();
        let today_summary_json = json_data.as_object().unwrap().get("summary").unwrap();
        let batches_json = json_data
            .as_object()
            .unwrap()
            .get("batches")
            .unwrap()
            .as_array()
            .unwrap();
        let mut batches: Vec<Batch> = batches_json
            .iter()
            .map(|value| Batch {
                id: value.get("id").unwrap().as_str().unwrap().to_owned(),
                area_collected: value
                    .get("area_collected")
                    .unwrap()
                    .as_str()
                    .map(|value| value.to_owned()),
                time_started: Local
                    .from_local_datetime(
                        &NaiveDateTime::from_str(
                            value.get("time_started").unwrap().as_str().unwrap(),
                        )
                        .unwrap(),
                    )
                    .unwrap(),
                time_submitted: Local
                    .from_local_datetime(
                        &NaiveDateTime::from_str(
                            value.get("time_submitted").unwrap().as_str().unwrap(),
                        )
                        .unwrap(),
                    )
                    .unwrap(),
                count: Count::from_json(&value),
                yolo_model: value
                    .get("yolo_model")
                    .unwrap()
                    .as_str()
                    .unwrap()
                    .to_owned(),
                category_model: value
                    .get("category_model")
                    .unwrap()
                    .as_str()
                    .unwrap()
                    .to_owned(),
            })
            .collect();
        batches.sort_by(|a, b| b.time_submitted.cmp(&a.time_submitted));
        Self {
            today_summary: TodaySummary {
                count: Count::for_today_summary(today_summary_json),
                num_of_batches: today_summary_json
                    .get("num_of_batches")
                    .unwrap()
                    .as_u64()
                    .unwrap(),
                num_of_batches_with_expected: today_summary_json
                    .get("num_of_batches_with_expected")
                    .unwrap()
                    .as_u64()
                    .unwrap(),
            },
            batches,
        }
    }

    fn merge(&mut self, old: &BatchGlobalState) {
        self.batches.extend(old.batches.clone());
        self.batches
            .sort_by(|a, b| b.time_submitted.cmp(&a.time_submitted));
    }
}

impl Clone for BatchGlobalState {
    fn clone(&self) -> Self {
        Self {
            today_summary: self.today_summary.clone(),
            batches: self.batches.clone(),
        }
    }
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
