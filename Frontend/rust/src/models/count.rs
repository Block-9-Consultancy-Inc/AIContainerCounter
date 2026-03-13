use chrono::{DateTime, Local, NaiveDateTime, TimeZone};
use flutter_rust_bridge::frb;
use serde_json::Value;
use std::str::FromStr;

use super::multi_container_image::{MultiContainerImage, SingleContainerImage};

#[derive(Clone)]
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

    #[frb(ignore)]
    pub fn from_json(json_data: &Value) -> Self {
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

    #[frb(ignore)]
    pub fn for_today_summary(json_data: &Value) -> Self {
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
        Some(
            (1.0 - ((actual.abs_diff(expected.unwrap()) as f64) / (expected.unwrap() as f64)))
                * 100.0,
        )
    }
}

#[derive(Clone)]

pub struct TodaySummary {
    pub num_of_batches: u64,
    pub num_of_batches_with_expected: u64,
    pub count: Count,
}

impl TodaySummary {
    fn updated_accuracy(
        avg_accuracy: Option<f64>,
        num_of_batches_with_expected: u64,
        new_accuracy: Option<f64>,
    ) -> Option<f64> {
        if avg_accuracy.is_none() || new_accuracy.is_none() {
            return None;
        }
        return Some(
            (avg_accuracy.unwrap() * (num_of_batches_with_expected as f64) + new_accuracy.unwrap())
                / (num_of_batches_with_expected + 1) as f64,
        );
    }

    #[frb(ignore)]
    pub fn update_with_batch(&mut self, batch: &Batch) {
        self.count.count += batch.count.count;
        self.count.can_count += batch.count.can_count;
        self.count.plastic_count += batch.count.plastic_count;
        self.count.drinkbox_count += batch.count.drinkbox_count;
        self.count.gabletop_count += batch.count.gabletop_count;
        self.count.pouch_count += batch.count.pouch_count;
        self.num_of_batches += 1;

        if self.count.count_accuracy.is_some() && batch.count.count_accuracy.is_some() {
            self.count.count_accuracy = Self::updated_accuracy(
                self.count.count_accuracy,
                self.num_of_batches_with_expected,
                batch.count.count_accuracy,
            );
        } else if self.count.count_accuracy.is_none() && batch.count.count_accuracy.is_some() {
            self.count.count_accuracy = batch.count.count_accuracy;
        }

        if self.count.can_accuracy.is_some() && batch.count.can_accuracy.is_some() {
            self.count.can_accuracy = Self::updated_accuracy(
                self.count.can_accuracy,
                self.num_of_batches_with_expected,
                batch.count.can_accuracy,
            );
        } else if self.count.can_accuracy.is_none() && batch.count.can_accuracy.is_some() {
            self.count.can_accuracy = batch.count.can_accuracy;
        }

        if self.count.plastic_accuracy.is_some() && batch.count.plastic_accuracy.is_some() {
            self.count.plastic_accuracy = Self::updated_accuracy(
                self.count.plastic_accuracy,
                self.num_of_batches_with_expected,
                batch.count.plastic_accuracy,
            );
        } else if self.count.plastic_accuracy.is_none() && batch.count.plastic_accuracy.is_some() {
            self.count.plastic_accuracy = batch.count.plastic_accuracy;
        }

        if self.count.drinkbox_accuracy.is_some() && batch.count.drinkbox_accuracy.is_some() {
            self.count.drinkbox_accuracy = Self::updated_accuracy(
                self.count.drinkbox_accuracy,
                self.num_of_batches_with_expected,
                batch.count.drinkbox_accuracy,
            );
        } else if self.count.drinkbox_accuracy.is_none() && batch.count.drinkbox_accuracy.is_some()
        {
            self.count.drinkbox_accuracy = batch.count.drinkbox_accuracy;
        }

        if self.count.gabletop_accuracy.is_some() && batch.count.gabletop_accuracy.is_some() {
            self.count.gabletop_accuracy = Self::updated_accuracy(
                self.count.gabletop_accuracy,
                self.num_of_batches_with_expected,
                batch.count.gabletop_accuracy,
            );
        } else if self.count.gabletop_accuracy.is_none() && batch.count.gabletop_accuracy.is_some()
        {
            self.count.gabletop_accuracy = batch.count.gabletop_accuracy;
        }

        if self.count.pouch_accuracy.is_some() && batch.count.pouch_accuracy.is_some() {
            self.count.pouch_accuracy = Self::updated_accuracy(
                self.count.pouch_accuracy,
                self.num_of_batches_with_expected,
                batch.count.pouch_accuracy,
            );
        } else if self.count.pouch_accuracy.is_none() && batch.count.pouch_accuracy.is_some() {
            self.count.pouch_accuracy = batch.count.pouch_accuracy;
        }

        if batch.count.count_accuracy.is_some() {
            self.num_of_batches_with_expected += 1;
        }
    }
}

#[derive(Clone)]
pub struct Batch {
    pub id: String,
    pub area_collected: Option<String>,
    pub time_started: DateTime<Local>,
    pub time_submitted: DateTime<Local>,
    pub count: Count,
    pub yolo_model: String,
    pub category_model: String,
    pub multi_container_images: Vec<MultiContainerImage>,
    pub single_container_images: Vec<SingleContainerImage>,
}

impl Batch {
    #[frb(ignore)]
    pub fn from_json(value: &Value) -> Self {
        let single_container_images: Vec<SingleContainerImage> = if value
            .get("singleContainerImages")
            .map_or(true, |v| v.is_null())
        {
            Vec::new()
        } else {
            value
                .get("singleContainerImages")
                .unwrap()
                .as_array()
                .unwrap()
                .into_iter()
                .map(|value| SingleContainerImage::from_json(value))
                .collect()
        };

        let multi_container_images: Vec<MultiContainerImage> = if value
            .get("multiContainerImages")
            .map_or(true, |v| v.is_null())
        {
            Vec::new()
        } else {
            value
                .get("multiContainerImages")
                .unwrap()
                .as_array()
                .unwrap()
                .into_iter()
                .map(|value| MultiContainerImage::from_json(value))
                .collect()
        };
        Self {
            id: value.get("id").unwrap().as_str().unwrap().to_owned(),
            area_collected: value
                .get("area_collected")
                .unwrap()
                .as_str()
                .map(|value| value.to_owned()),
            time_started: Local
                .from_local_datetime(
                    &NaiveDateTime::from_str(value.get("time_started").unwrap().as_str().unwrap())
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
            single_container_images,
            multi_container_images
        }
    }
}

#[derive(Clone)]
pub enum StateUpdate {
    BatchFetch {
        batch: Batch
    },
    BatchGlobalState{
        batch_global_state: BatchGlobalState
    },
}

#[derive(Clone)]
pub struct BatchGlobalState {
    pub today_summary: TodaySummary,
    pub batches: Vec<Batch>,
    pub update_summary: bool,
}

impl BatchGlobalState {
    #[frb(ignore)]
    pub fn from_json(json_data: &Value) -> Self {
        let update_summary = json_data
            .get("update_summary")
            .unwrap()
            .as_bool()
            .unwrap_or(false);
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
            .map(|value| Batch::from_json(value))
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
            update_summary,
        }
    }

    #[frb(ignore)]
    pub fn merge(&mut self, old: &BatchGlobalState) {
        if self.update_summary {
            for batch in self.batches.iter() {
                self.today_summary.update_with_batch(batch);
            }
        }
        self.batches.extend(old.batches.clone());
    }
}
