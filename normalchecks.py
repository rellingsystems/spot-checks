#!/usr/bin/env python3
"""
Generate spot check overlays for _annotated_720p videos only.
- Reads from perfect_frame_annotation.json
- Extracts frames from _annotated_720p videos
- Overlays annotation points on the frames
"""

import cv2
import json
import os
import subprocess
import argparse

# S3 base path
S3_BASE = "s3://rellingxgdm-raw/rellingxgdm-raw/rellingxgdm-raw/CLIPPED"

OUTPUT_DIR = "/Users/anyasingh/samfinal/samsbody/HANDS/final_spot_checks"


def download_file(s3_path, local_path):
    """Download file from S3."""
    cmd = f'aws s3 cp "{s3_path}" "{local_path}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode == 0


def extract_frame_from_s3(s3_video_path, frame_num, output_path):
    """Extract a single frame from S3 video using ffmpeg with S3 streaming."""
    # Get presigned URL
    presign_cmd = f'aws s3 presign "{s3_video_path}" --expires-in 3600'
    result = subprocess.run(presign_cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  Failed to presign: {result.stderr}")
        return False

    presigned_url = result.stdout.strip()

    # Use ffmpeg to extract frame (assume 30fps)
    ffmpeg_cmd = [
        'ffmpeg', '-y',
        '-ss', str(frame_num / 30.0),
        '-i', presigned_url,
        '-frames:v', '1',
        '-f', 'image2',
        output_path
    ]

    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    return result.returncode == 0 and os.path.exists(output_path)


def draw_annotations(frame, json_data):
    """Draw JSON annotation points on frame."""
    h, w = frame.shape[:2]

    colors = {
        'obj1_positive_points': (255, 0, 255),    # Magenta
        'obj1_negative_points': (255, 0, 255),    # Magenta
        'obj2_positive_points': (0, 255, 255),    # Cyan
        'obj2_negative_points': (0, 255, 255),    # Cyan
        'positive_points': (0, 255, 0),           # Green
        'negative_points': (0, 0, 255),           # Red
    }

    for key, color in colors.items():
        if key not in json_data:
            continue

        for pt in json_data[key]:
            x, y = int(pt[0]), int(pt[1])

            # Only draw if within frame bounds
            if 0 <= x < w and 0 <= y < h:
                if 'positive' in key:
                    # Filled circle with + symbol
                    cv2.circle(frame, (x, y), 12, color, -1)
                    cv2.circle(frame, (x, y), 12, (255, 255, 255), 2)
                    cv2.putText(frame, "+", (x-6, y+6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                else:
                    # X mark
                    cv2.line(frame, (x-12, y-12), (x+12, y+12), color, 3)
                    cv2.line(frame, (x+12, y-12), (x-12, y+12), color, 3)

    return frame


def add_legend(frame, video_name, frame_num):
    """Add legend to frame."""
    # Background
    cv2.rectangle(frame, (10, 10), (450, 130), (0, 0, 0), -1)
    cv2.rectangle(frame, (10, 10), (450, 130), (255, 255, 255), 1)

    # Title
    cv2.putText(frame, f"{video_name}", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

    # Frame info
    cv2.putText(frame, f"Frame: {frame_num} | Source: _annotated_720p",
                (15, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

    # Legend items
    cv2.circle(frame, (25, 75), 8, (255, 0, 255), -1)
    cv2.putText(frame, "Obj1 +/-", (40, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 255), 1)

    cv2.circle(frame, (150, 75), 8, (0, 255, 255), -1)
    cv2.putText(frame, "Obj2 +/-", (165, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

    cv2.circle(frame, (25, 100), 8, (0, 255, 0), -1)
    cv2.putText(frame, "Positive", (40, 103), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

    cv2.circle(frame, (150, 100), 8, (0, 0, 255), -1)
    cv2.putText(frame, "Negative", (165, 103), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

    return frame


def process_video(category, video_name, json_data, output_dir):
    """Process a single video from the JSON annotations."""
    print(f"\n{'='*60}")
    print(f"Processing: {video_name}")
    print(f"{'='*60}")

    s3_folder = f"{S3_BASE}/{category}/{video_name}"

    # Get frame numbers from JSON
    frame_nums = list(json_data.keys())
    if not frame_nums:
        print(f"  ERROR: No frames in JSON for {video_name}")
        return False

    frame_num = int(frame_nums[0])
    print(f"  Target frame: {frame_num}")

    # Build _annotated_720p video path
    video_file = f"{video_name}_annotated_720p.mp4"
    s3_video_path = f"{s3_folder}/{video_file}"
    print(f"  Video file: {video_file}")

    # Extract frame
    frame_path = os.path.join(output_dir, f"{video_name}_frame_temp.png")
    print(f"  Extracting frame from {video_file}...")

    if not extract_frame_from_s3(s3_video_path, frame_num, frame_path):
        print(f"  ERROR: Failed to extract frame from {video_file}")
        return False

    # Load frame
    frame = cv2.imread(frame_path)
    if frame is None:
        print(f"  ERROR: Failed to load extracted frame")
        return False

    print(f"  Frame size: {frame.shape[1]}x{frame.shape[0]}")

    # Draw annotations
    frame = draw_annotations(frame, json_data[frame_nums[0]])

    # Add legend
    frame = add_legend(frame, video_name, frame_num)

    # Save
    output_path = os.path.join(output_dir, f"{video_name}_annotated_spot_check.png")
    cv2.imwrite(output_path, frame)
    print(f"  Saved: {output_path}")

    # Cleanup temp file
    if os.path.exists(frame_path):
        os.remove(frame_path)

    return True


def main():
    parser = argparse.ArgumentParser(description='Generate spot checks for _annotated_720p videos')
    parser.add_argument('--json', type=str, default='perfect_frame_annotation.json',
                        help='Path to the JSON annotation file')
    parser.add_argument('--output', type=str, default=OUTPUT_DIR,
                        help='Output directory for spot check images')
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    print("=" * 60)
    print("SPOT CHECK GENERATOR - _annotated_720p Videos Only")
    print("=" * 60)

    # Load JSON annotation file
    json_path = args.json
    if not os.path.isabs(json_path):
        # Check in current directory and output directory
        if os.path.exists(json_path):
            pass
        elif os.path.exists(os.path.join(args.output, json_path)):
            json_path = os.path.join(args.output, json_path)
        else:
            print(f"ERROR: JSON file not found: {json_path}")
            return

    print(f"Loading annotations from: {json_path}")

    with open(json_path, 'r') as f:
        all_annotations = json.load(f)

    print(f"Found {len(all_annotations)} video(s) in annotations")

    successful = 0
    failed = 0

    # Process each video in the JSON
    for video_key, video_data in all_annotations.items():
        # Extract category and video name from the key
        # Expected format: "category/video_name" or just "video_name"
        if '/' in video_key:
            category, video_name = video_key.rsplit('/', 1)
        else:
            # Try to infer category from video name
            video_name = video_key
            # Common category patterns
            category_patterns = [
                'motorcycle_repair', 'assembling_motor_starter', 'adjusting_vehicle_tire',
                'baking', 'candy', 'clay', 'ac_maintenance', 'fan_assembly',
                'professionalchef', 'panel_assembly', 'construction_wirework',
                'building_bookshelf', 'air_purifier_deep_clean', 'installing_car_speakers',
                'mosaic_number_tiles', 'washing_clothes'
            ]
            category = None
            for pattern in category_patterns:
                if video_name.startswith(pattern):
                    category = pattern
                    break
            if category is None:
                # Use first part before _seq as category
                parts = video_name.split('_seq')
                if len(parts) > 1:
                    category = parts[0]
                else:
                    print(f"  WARNING: Could not determine category for {video_name}, skipping")
                    failed += 1
                    continue

        try:
            if process_video(category, video_name, {str(k): v for k, v in video_data.items()} if isinstance(video_data, dict) and not any(k in video_data for k in ['positive_points', 'negative_points', 'obj1_positive_points']) else {'0': video_data}, args.output):
                successful += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*60}")
    print(f"DONE: {successful} successful, {failed} failed")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
