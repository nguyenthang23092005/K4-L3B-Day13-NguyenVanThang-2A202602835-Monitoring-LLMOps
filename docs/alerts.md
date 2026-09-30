# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert mẫu để tham khảo

Ví dụ dưới đây minh họa mức độ cụ thể cần có. Học viên không cần copy nguyên, nhưng ba alert trong bài nộp nên rõ ràng tương tự: điều kiện là gì, kéo dài bao lâu, ảnh hưởng tới user ra sao và người trực cần kiểm tra gì trước.

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: latency P95 của `response_sent.latency_ms`
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` trong 5 phút
- Ảnh hưởng tới người dùng: người dùng phải chờ lâu hơn trước khi nhận câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard latency để xác nhận P95/P99 và khoảng thời gian tăng.
  2. Lọc `data/logs.jsonl` trong khoảng đó, lấy một `correlation_id` có `latency_ms` cao.
  3. Mở trace cùng `correlation_id` trên Langfuse, so sánh các span chính để xác định bước nào bất thường.
- Mitigation tạm thời: dựa trên evidence thực tế để rollback prompt, khôi phục cấu hình liên quan, tắt practice scenario hoặc giảm tải khi demo.
- Owner: `student-<MSSV>`

## Alert 1

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: latency P95 của các event `response_sent` và SLO request hoàn thành trong 3000 ms.
- Điều kiện và thời gian duy trì: `p95(response_sent.latency_ms) > 3000 ms` liên tục trong 5 phút.
- Ảnh hưởng tới người dùng: phần lớn người dùng phải chờ lâu hơn ngưỡng SLO để nhận câu trả lời.
- Ba bước kiểm tra đầu tiên:
  1. Mở panel Latency, xác nhận P95/P99, TTFT P95 và khoảng thời gian vượt ngưỡng.
  2. Lọc `response_sent` có `latency_ms > 3000` trong `data/logs.jsonl`, lấy `correlation_id` đại diện.
  3. Mở trace cùng `correlation_id` trên Langfuse và so sánh thời gian của `retrieval` với `generation`.
- Mitigation tạm thời: tắt practice incident nếu đang bật; nếu generation chậm sau đổi prompt thì rollback label `production`, còn nếu retrieval chậm thì giảm tải và khôi phục nguồn retrieval ổn định.
- Owner: `student-nguyen-van-thang`

## Alert 2

- Tên: `HighRequestErrorRate`
- Severity: `critical`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: error rate và SLO 99.5% request thành công, nhanh hơn 3000 ms.
- Điều kiện và thời gian duy trì: `request_failed / request_received * 100 > 2%` liên tục trong 5 phút.
- Ảnh hưởng tới người dùng: hơn 2% yêu cầu không nhận được câu trả lời thành công.
- Ba bước kiểm tra đầu tiên:
  1. Mở panel Errors, xác nhận error rate và nhóm `error_type` đang tăng.
  2. Lọc các event `request_failed` trong `data/logs.jsonl`, chọn một `correlation_id` và xem `tool_name`, `tool_success`.
  3. Mở trace cùng `correlation_id`, xác định child observation lỗi và thông báo lỗi liên quan.
- Mitigation tạm thời: tắt scenario gây lỗi, rollback thay đổi gần nhất và chuyển sang fallback an toàn nếu dependency chưa phục hồi.
- Owner: `student-nguyen-van-thang`

## Alert 3

- Tên: `LowRetrievalSuccessRate`
- Severity: `warning`
- Duration: `10m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: retrieval success rate tối thiểu 90%.
- Điều kiện và thời gian duy trì: `tool_success == true / tool_success != null * 100 < 90%` liên tục trong 10 phút.
- Ảnh hưởng tới người dùng: câu trả lời thiếu context hoặc request thất bại do không lấy được tài liệu.
- Ba bước kiểm tra đầu tiên:
  1. Mở panel Errors, xác nhận retrieval success giảm dưới 90% và đối chiếu error rate.
  2. Lọc mọi event có field `tool_success`, sau đó lấy `correlation_id` của bản ghi `tool_success=false`.
  3. Mở trace cùng `correlation_id`, kiểm tra observation `retrieval` và so sánh với trace thành công gần nhất.
- Mitigation tạm thời: tắt practice incident, dùng context fallback hoặc tạm giảm lưu lượng tới retrieval dependency cho đến khi health check ổn định.
- Owner: `student-nguyen-van-thang`
