# Protocol Evaluation: FocusFlow DeepForest

Tài liệu này quy định các thí nghiệm cần chạy trước khi đưa số liệu vào luận
văn hoặc slide. Không điền số minh họa vào bảng kết quả.

## 1. Phạm vi và claim

FocusFlow dự đoán nhãn engagement quan sát được trong DAiSEE, không đo trực
tiếp trạng thái nhận thức hay năng suất thật của người dùng. Feature telemetry
là dữ liệu suy ra từ sinh trắc học; không gửi frame không đồng nghĩa dữ liệu
hoàn toàn vô danh.

Model product là `deep_forest_product_4class`, được đánh giá trên protocol
DAiSEE đã lưu trong artifact. Các chỉ số artifact: accuracy 76.85%, balanced
accuracy 85.90%, macro-F1 78.02%. Những số này không phải cam kết cho camera,
ánh sáng hoặc người dùng mới.

## 2. Ablation study

Mục tiêu là định lượng, không giả định, đóng góp của từng nhóm feature trong
schema `depth_robust_v2`.

| Variant | Nhóm bị mask | Câu hỏi |
|---|---|---|
| Full | Không | Mốc baseline |
| A1 | `geometry` | EAR/MAR, pose proxy và distance/depth proxy đóng góp gì? |
| A2 | `canonical_landmarks` | Landmark canonicalized có ích không? |
| A3 | `blendshapes` | MediaPipe blendshapes có cải thiện không? |
| A4 | `transform` | Facial transformation matrix có cải thiện không? |
| A5 | từng cặp nhóm | Hiệu ứng kết hợp và redundancy |

Mỗi variant phải giữ nguyên video-level train/validation/test split, seed,
classifier hyperparameters và calibration policy. Chỉ thay dữ liệu feature.

```bash
python scripts/ablate_depth_robust_v2.py \
  --manifest ../engagement-cpu/.tmp/hf_processed_meta/final_feature_manifest.csv \
  --output-dir /tmp/focusflow-ablation/a1-geometry \
  --drop geometry
```

Sau đó train lại cùng lệnh DeepForest trong `engagement-cpu`. Báo cáo accuracy,
balanced accuracy, macro-F1, precision/recall theo lớp và latency cho mọi
variant; không chỉ báo variant tốt nhất.

## 3. Raw-video end-to-end latency

Không dùng model-side latency thay cho trải nghiệm người dùng. Chạy benchmark
trên ít nhất một video demo và một webcam thật, ghi CPU/RAM/OS, camera, độ phân
giải, FPS và mạng.

```bash
# Model-side evaluation và MediaPipe trên cùng máy, không thay đổi product mode.
python scripts/benchmark_raw_video_e2e.py \
  --video demo/Data/01.mp4 \
  --local-model \
  --windows 50 \
  --output demo/results/e2e-local-01.json

# End-to-end edge-to-cloud thật sau khi Cloud Run deploy revision tương ứng.
python scripts/benchmark_raw_video_e2e.py \
  --video demo/Data/01.mp4 \
  --cloud \
  --windows 50 \
  --output demo/results/e2e-cloud-01.json
```

Report phân biệt `extraction`, `client_loop`, `local_model` và
`cloud_roundtrip` bằng mean/median/p95/max. Không cộng các percentile riêng lẻ
để suy ra p95 end-to-end.

## 4. Generalization ngoài DAiSEE

Thu thập một evaluation set có consent, tách người theo subject-disjoint split:

- ít nhất 3 camera hoặc webcam;
- ánh sáng: sáng đều, tối, backlight;
- góc: chính diện, yaw/pitch vừa phải;
- khoảng cách: gần, trung bình, xa;
- có/không kính và các background điển hình.

Mỗi segment cần một protocol nhãn rõ ràng: task có ground truth hành vi hoặc
rating đa người chấm, kèm agreement. Không gọi nhãn là "tập trung thật" khi
chỉ có external observation. Báo cáo metric theo từng condition và confidence
interval bootstrap theo video/person.

## 5. Privacy và offline

Cloud-only demo hiện tại giảm truyền raw video và tập trung lifecycle,
observability, persistence và scale Cloud Run. Nó không phải "privacy tuyệt
đối" vì `(30,168)` vẫn là biometric-derived telemetry. Production cần TLS,
short-lived user token, least-privilege service account, retention/deletion
policy và consent UI.

DeepForest product được benchmark riêng trên CPU, nhưng quyết định local-only
hay cloud phải dựa trên raw-video E2E, RAM/bundle size, battery, update policy
và reliability; không chỉ dựa vào model-side latency. Một local/offline mode là
hướng product hợp lý nếu các benchmark và threat model chứng minh được nó.
