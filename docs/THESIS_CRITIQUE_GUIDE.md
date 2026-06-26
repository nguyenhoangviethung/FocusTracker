# FocusFlow AI: Hướng Dẫn Trả Lời Phản Biện

## Model và claim

Runtime hiện tại là `deep_forest_product_4class`: accuracy 76.85%, balanced
accuracy 85.90%, macro-F1 78.02% trên protocol DAiSEE được lưu cùng artifact.
Đây là chỉ số dataset-bound, không phải độ chính xác được cam kết ngoài đời.

Model dùng `depth_robust_v2`: 168 feature/frame, `(30,168)` raw window,
velocity/std enrichment `(30,504)`, basic aggregate 3529D, rồi cascade
ExtraTrees + RandomForest hai tầng và calibration 4 lớp.

## Ba câu hỏi cốt lõi

**1. Cơ sở nào để chọn feature?**

Không nên nói bộ feature là tối ưu nếu chưa có ablation. Cơ sở thiết kế là
EAR/MAR cho opening mắt/miệng, hình học canonical theo inter-eye/roll để giảm
camera-distance sensitivity, depth proxy/iris và MediaPipe blendshape/transform
để mở rộng tín hiệu biểu cảm-hình học. Đây là hypothesis kỹ thuật, không phải
bằng chứng tối ưu. `docs/EVALUATION_PROTOCOL.md` và
`scripts/ablate_depth_robust_v2.py` là protocol để kiểm định từng nhóm, giữ
nguyên split và classifier.

**2. Tại sao không local-only?**

Phiên bản demo dùng cloud để đánh giá REST/WebSocket, session persistence,
Cloud Run scale và observability; nó chỉ giảm raw-video upload, không được gọi
là privacy tuyệt đối. Telemetry `(30,168)` vẫn nhạy cảm. Model-side latency
không đủ để kết luận local mode tốt hơn vì MediaPipe, RAM, kích thước bundle,
battery, update/revocation và reliability còn chi phối. Hướng production là
đánh giá local/offline mode bằng cùng raw-video benchmark và threat model; API
key tĩnh chỉ chấp nhận cho demo, không phải production auth.

**3. Generalization và end-to-end?**

Không khẳng định generalization khi chưa có test subject-disjoint ngoài DAiSEE.
Luận văn phải báo đây là giới hạn. Hệ thống đã có benchmark đo extraction,
client loop, local-model evaluation và cloud round-trip từ video thô; kết quả
chỉ được đưa vào báo cáo sau khi chạy trên camera/lighting/network được ghi
nhận. Không thay raw-video E2E bằng model-side latency.

## Các giới hạn phải nói rõ

- DAiSEE là external/crowd annotation; model học nhãn engagement quan sát được,
  không đo trực tiếp cognitive focus.
- Cửa sổ 30 frame là mẫu telemetry ngắn, không là kết luận tâm lý độc lập.
  UI/report cần smoothing hoặc aggregation theo thời gian dài hơn.
- Không gửi frame không loại bỏ rủi ro biometric telemetry.
- Kết quả benchmark và model selection phải gắn artifact hash, model version,
  source commit, hardware và protocol.
