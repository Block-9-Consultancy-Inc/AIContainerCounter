use std::str::FromStr;
use chrono::{DateTime, Local, NaiveDateTime, TimeZone};
use flutter_rust_bridge::frb;
use serde_json::{Map, Value};

#[derive(Clone)]
pub struct AuthorizedUser {
    pub id: String,
    pub name: String,
    pub signed_in_time: DateTime<Local>
}

impl AuthorizedUser {
    #[frb(ignore)]
    pub fn from_json(value: &Map<String, Value>) -> Self {
        Self {
            id: value.get("user_id").unwrap().as_str().unwrap().to_owned(),
            name: value.get("user_name").unwrap().as_str().unwrap().to_owned(),
            signed_in_time: Local
                .from_local_datetime(
                    &NaiveDateTime::from_str(
                        value.get("signed_in_time").unwrap().as_str().unwrap(),
                    )
                    .unwrap(),
                )
                .unwrap(),
        }
    }
}