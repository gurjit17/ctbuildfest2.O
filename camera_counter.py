
"""Camera-only object tracking and unique counting."""
import time

from app.classification import category_bin, rule_for


class CameraCounter:
    def __init__(self, min_hits=3, max_missing=1.5):
        self.min_hits = min_hits
        self.max_missing = max_missing

        self.tracks = {}
        self.next_id = 1
        self.last_frame_key = None

        self.counts = {
            "total": 0,
            "wet": 0,
            "dry": 0,
            "special": 0,
            "sharps": 0,
            "unclassified": 0,
            "bin1": 0,
            "bin2": 0,
            "bin3": 0,
            "by_label": {},
        }

    @staticmethod
    def center(bbox):
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    @staticmethod
    def distance(a, b):
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    @staticmethod
    def iou(box_a, box_b):
        ax1, ay1, ax2, ay2 = box_a
        bx1, by1, bx2, by2 = box_b

        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)

        intersection = max(0, ix2 - ix1) * max(0, iy2 - iy1)

        area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
        area_b = max(0, bx2 - bx1) * max(0, by2 - by1)

        union = area_a + area_b - intersection
        return intersection / union if union else 0.0

    def classify(self, label):
        rule = rule_for(label)

        if rule is None or rule.category is None:
            return None, None

        category = rule.category
        bin_number, _ = category_bin(category)

        return category, bin_number

    def count_track(self, track):
        label = track["label"]
        category, bin_number = self.classify(label)

        self.counts["total"] += 1

        self.counts["by_label"][label] = (
            self.counts["by_label"].get(label, 0) + 1
        )

        if category is None:
            self.counts["unclassified"] += 1
            return

        self.counts[category.value] += 1
        self.counts[f"bin{bin_number}"] += 1

    def update(self, detections, frame_key=None):
        now = time.monotonic()

        # Do not count the same camera frame repeatedly.
        if frame_key is not None and frame_key == self.last_frame_key:
            return self.snapshot()

        self.last_frame_key = frame_key

        matched = set()

        for detection in detections:
            label = detection.label
            bbox = detection.bbox
            center = self.center(bbox)

            best_id = None
            best_score = 0.0

            for track_id, track in self.tracks.items():
                if track_id in matched:
                    continue

                if track["label"] != label:
                    continue

                if now - track["last_seen"] > self.max_missing:
                    continue

                overlap = self.iou(bbox, track["bbox"])
                dist = self.distance(center, track["center"])

                x1, y1, x2, y2 = bbox
                threshold = max(45, 0.5 * max(x2 - x1, y2 - y1))

                if overlap >= 0.1 or dist <= threshold:
                    score = overlap + max(0, 1 - dist / threshold) * 0.5

                    if score > best_score:
                        best_score = score
                        best_id = track_id

            if best_id is None:
                best_id = self.next_id
                self.next_id += 1

                self.tracks[best_id] = {
                    "label": label,
                    "bbox": bbox,
                    "center": center,
                    "hits": 0,
                    "last_seen": now,
                    "counted": False,
                }

            track = self.tracks[best_id]

            track["bbox"] = bbox
            track["center"] = center
            track["last_seen"] = now
            track["hits"] += 1

            matched.add(best_id)

            if track["hits"] >= self.min_hits and not track["counted"]:
                track["counted"] = True
                self.count_track(track)

        # Remove disappeared objects.
        self.tracks = {
            track_id: track
            for track_id, track in self.tracks.items()
            if now - track["last_seen"] <= self.max_missing
        }

        return self.snapshot()

    def snapshot(self):
        return {
            **self.counts,
            "by_label": dict(self.counts["by_label"]),
            "active_tracks": len(self.tracks),
        }

