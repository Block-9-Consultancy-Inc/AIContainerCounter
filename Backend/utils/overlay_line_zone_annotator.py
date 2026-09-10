#!/usr/bin/env python3
import sys
import numpy as np
import cv2
import supervision as sv
from ultralytics import YOLO
import gi

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject, GLib


class OverlayLineZoneAnnotator:
    """
    Same annotator as before, using cv2 to draw on numpy frames.
    """
    def __init__(
        self,
        line_zone: sv.LineZone,
        shadow_height: int = 50,
        line_color: tuple[int,int,int] = (255, 255, 255),
        text_color: tuple[int,int,int] = (255, 255, 255),
        cross_color: tuple[int,int,int] = (0, 255, 0),
        thickness: int = 2,
        font_scale: float = 0.6,
        shadow_color: tuple[int,int,int] = (0, 0, 0),
        shadow_alpha: float = 0.6,
    ):
        self.line_zone_start = line_zone.vector.start
        self.line_zone_end = line_zone.vector.end
        self.line_zone_class_names = line_zone.class_id_to_name
        self.shadow_height = shadow_height
        self.line_color = line_color
        self.text_color = text_color
        self.cross_color = cross_color
        self.thickness = thickness
        self.font_scale = font_scale
        self.shadow_color = shadow_color
        self.shadow_alpha = shadow_alpha
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.crossed_ids: dict[int, int] = {}
        self.next_order: int = 1

    def reset(self):
        self.crossed_ids = {}
        self.next_order = 1

    def annotate(self, frame: np.ndarray, crossed_in: np.ndarray, detections: sv.Detections, overall_count: int, counts: dict[str, int], labels: list[str] = None) -> np.ndarray:
        for idx, did in enumerate(crossed_in):
            if not did:
                continue
            tid = detections.tracker_id[idx]
            if tid is None or tid in self.crossed_ids:
                continue
            self.crossed_ids[tid] = self.next_order
            self.next_order += 1

        h, w = frame.shape[:2]
        cv2.line(
            frame,
            (int(self.line_zone_start.x), int(self.line_zone_start.y)),
            (int(self.line_zone_end.x),   int(self.line_zone_end.y)),
            self.line_color, self.thickness * 2
        )

        for idx, (box, cls_id) in enumerate(zip(detections.xyxy, detections.class_id)):
            x1, y1, x2, y2 = box.astype(int)
            cx, cy = (x1 + x2)//2, (y1 + y2)//2
            cv2.circle(frame, (cx, cy), 20, self.text_color, -1)
            name = self.line_zone_class_names.get(cls_id, str(cls_id)) if labels is None else labels[idx]
            cv2.putText(frame, name, (x1, y1 - 10), self.font, self.font_scale, self.text_color, self.thickness)
            tid = detections.tracker_id[idx]
            if tid in self.crossed_ids:
                size = 10
                cv2.line(frame, (cx-size, cy-size), (cx+size, cy+size), self.cross_color, self.thickness)
                cv2.line(frame, (cx-size, cy+size), (cx+size, cy-size), self.cross_color, self.thickness)
                order = self.crossed_ids[tid]
                cv2.putText(frame, str(order), (cx+size+8, cy+size+8), self.font, self.font_scale * 1.5, self.cross_color, self.thickness)

        overlay = frame.copy()
        rect_top = h - self.shadow_height
        cv2.rectangle(overlay, (0, rect_top), (w, h), self.shadow_color, -1)
        cv2.addWeighted(overlay, self.shadow_alpha, frame, 1 - self.shadow_alpha, 0, frame)

        texts = [f"Total: {overall_count}"] + [f"{cid}: {cnt}" for cid, cnt in counts.items()]
        n = len(texts)
        for i, text in enumerate(texts):
            (tw, th), _ = cv2.getTextSize(text, self.font, self.font_scale, self.thickness)
            x = int((i + 0.5) * w / n - tw / 2)
            y = rect_top + int((self.shadow_height + th) / 2)
            cv2.putText(frame, text, (x, y), self.font, self.font_scale, self.text_color, self.thickness)

        return frame


def gst_pad_probe(pad, info, user_data):
    """
    GstPadProbe callback: gets called per buffer.
    """
    frame_meta = info.get_buffer()
    success, map_info = frame_meta.map(Gst.MapFlags.READ)
    if not success:
        return Gst.PadProbeReturn.OK
    try:
        # Extract raw bytes and reshape to numpy (BGR)
        buf = map_info.data
        # Retrieve width, height, stride from caps
        caps = pad.get_current_caps()
        structure = caps.get_structure(0)
        width = structure.get_value('width')
        height = structure.get_value('height')
        # Assuming format BGR
        arr = np.frombuffer(buf, np.uint8).copy()
        frame = arr.reshape((height, width, 3))

        # Run model inference and annotate
        result = user_data['model'](frame)[0]
        detections = sv.Detections.from_ultralytics(result)
        detections = user_data['byte_tracker'].update_with_detections(detections)
        crossed_in, _ = user_data['line_zone'].trigger(detections)

        annotated = user_data['annotator'].annotate(frame, crossed_in, detections)

        # cv2.imshow('Annotated Overlay Line Zone', annotated)
        # cv2.waitKey(1)
    finally:
        frame_meta.unmap(map_info)
    return Gst.PadProbeReturn.OK


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 script.py '<GStreamer pipeline>' <model-path>")
        sys.exit(1)

    Gst.init(None)
    pipeline_str = sys.argv[1]
    model_path = sys.argv[2] if len(sys.argv) > 2 else 'yolov8n.pt'

    # Initialize YOLO and annotator
    model = YOLO(model_path)
    # Dummy frame to get dims (optional if pipeline negotiates)
    # Here, assume user defines counting line in code or via args
    # Example: line at middle
    # After first buffer, you could set line dynamically, but here we hardcode after startup

    # Build pipeline
    pipeline = Gst.parse_launch(pipeline_str)

    # Retrieve the probe element by name 'probe'
    probe_elem = pipeline.get_by_name('probe')
    if not probe_elem:
        print("Error: element named 'probe' not found in pipeline")
        sys.exit(1)

    sink_pad = probe_elem.get_static_pad('sink')
    # Attach pad probe
    user_data = {
        'model': model,
        'byte_tracker': sv.ByteTrack(),
        'line_zone': None,
        'annotator': None  # Will initialize on first buffer
    }

    def first_buffer_probe(pad, info):
        # Initialize annotator once we know caps
        print('first buffer probe')
        buf = info.get_buffer()
        caps = pad.get_current_caps()
        struct = caps.get_structure(0)
        h = struct.get_value('height')
        w = struct.get_value('width')
        x = struct.get_value('width') // 2
        user_data['line_zone'] = sv.LineZone(start=sv.Point(x, 0), end=sv.Point(x, h))
        user_data['annotator'] = OverlayLineZoneAnnotator(user_data['line_zone'])
        # Replace this probe with main gst_pad_probe
        sink_pad.remove_probe(first_probe_id)
        sink_pad.add_probe(Gst.PadProbeType.BUFFER, gst_pad_probe, user_data)
        return Gst.PadProbeReturn.OK

    first_probe_id = sink_pad.add_probe(Gst.PadProbeType.BUFFER, first_buffer_probe)

    # Start pipeline
    pipeline.set_state(Gst.State.PLAYING)
    print("Pipeline playing. Press Ctrl+C to stop.")

    # Run main loop
    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.set_state(Gst.State.NULL)

if __name__ == '__main__':
    main()
