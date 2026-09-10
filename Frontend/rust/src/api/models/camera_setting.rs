use flutter_rust_bridge::frb;
use serde_json::Value;

#[derive(Clone)]
pub struct CameraSetting {
    pub id: String,
    pub value: i64,
    pub min: i64,
    pub max: i64,
    pub step: Option<i64>
}

impl CameraSetting {
    #[frb(ignore)]
    pub fn from_json(value: &Value) -> Self {
        Self {
            id: value.get("id").unwrap().as_str().unwrap().to_owned(),
            value: value.get("value").unwrap().as_i64().unwrap(),
            min: value.get("min").unwrap().as_i64().unwrap(),
            max: value.get("max").unwrap().as_i64().unwrap(),
            step: value.get("step").unwrap().as_i64(),
        }
    }
}