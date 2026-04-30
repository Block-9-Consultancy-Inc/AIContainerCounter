use std::str::FromStr;

use chrono::{DateTime, Local, NaiveDateTime, TimeZone};
use serde_json::Value;


#[derive(Clone)]
pub struct MultiContainerImage {
    pub id: String,
    pub height: i64,
    pub width: i64,
    pub index: i64,
    pub time_collected: DateTime<Local>,
    pub bboxes: Vec<BBox>,
}

#[derive(Clone)]
pub struct BBox {
    pub id: String,
    pub x1: i64,
    pub y1: i64,
    pub x2: i64,
    pub y2: i64,
    pub tracker_id: i64,
}

impl MultiContainerImage {

    #[flutter_rust_bridge::frb(ignore)]
    pub fn from_json(json_data: &Value) -> Self {
        let bboxes_json = json_data
            .get("bboxes")
            .unwrap()
            .as_array()
            .unwrap();
        let bboxes: Vec<BBox> = bboxes_json
            .iter()
            .map(|value| BBox {
                id: value.get("id").unwrap().as_str().unwrap().to_owned(),
                x1: value.get("x1").unwrap().as_i64().unwrap(),
                y1: value.get("y1").unwrap().as_i64().unwrap(),
                x2: value.get("x2").unwrap().as_i64().unwrap(),
                y2: value.get("y2").unwrap().as_i64().unwrap(),
                tracker_id: value.get("tracker_id").unwrap().as_i64().unwrap(),
            })
            .collect();
        Self {
            id: json_data.get("id").unwrap().as_str().unwrap().to_owned(),
            height: json_data.get("height").unwrap().as_i64().unwrap(),
            width: json_data.get("width").unwrap().as_i64().unwrap(),
            index: json_data.get("index").unwrap().as_i64().unwrap(),
            time_collected: Local
                    .from_local_datetime(
                        &NaiveDateTime::from_str(
                            json_data.get("time_collected").unwrap().as_str().unwrap(),
                        )
                        .unwrap(),
                    )
                    .unwrap(),
            bboxes,
        }
    }
}

#[derive(Clone)]
pub struct SingleContainerImage {
    pub id: String,
    pub height: i64,
    pub width: i64,
    pub time_collected: DateTime<Local>,
    pub tracker_id: i64,
    pub predicted_category: String,
}

impl SingleContainerImage {
    #[flutter_rust_bridge::frb(ignore)]
    pub fn from_json(json_data: &Value) -> Self {
        Self {
            id: json_data.get("id").unwrap().as_str().unwrap().to_owned(),
            height: json_data.get("height").unwrap().as_i64().unwrap(),
            width: json_data.get("width").unwrap().as_i64().unwrap(),
            tracker_id: json_data.get("tracker_id").unwrap().as_i64().unwrap(),
            time_collected: Local
                    .from_local_datetime(
                        &NaiveDateTime::from_str(
                            json_data.get("time_collected").unwrap().as_str().unwrap(),
                        )
                        .unwrap(),
                    )
                    .unwrap(),
            predicted_category: json_data.get("predicted_category").unwrap().as_str().unwrap().to_owned(),
        }
    }
}