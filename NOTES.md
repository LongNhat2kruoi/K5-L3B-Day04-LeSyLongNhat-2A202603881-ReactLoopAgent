# Ghi chú phân tích · Day 04

## 1. Case được chọn

- ID case: E1/E2 và H7.
- Lần chạy 1: E1 và E2 đạt 100; H7 đạt 50.
- Vấn đề hạ tầng: từ E3 trở đi xuất hiện HTTP 429 từ Gemini, khiến nhiều case không được chấm.

## 2. Bằng chứng trong trace

- CP2 smoke test hoàn tất với 2 model calls và 1.548 tokens.
- `eval_before.json`: 22 case, 7 scored, 15 unscored; `score_0_100: null`, `partial_mean_0_100: 92.86`.
- E3 có reason `Judge lỗi: Provider trả HTTP 429`; E4–A8 và H1–H3 có run error do cùng giới hạn hạ tầng.
- H7 đạt 50 vì agent không được phép kết luận Cloudflare operational khi tool timeout; đây là lỗi hành vi cần theo dõi.

## 3. Thay đổi đã thực hiện

- `agent.py`: hoàn thiện loop, xử lý nhiều tool calls, lỗi JSON/tool/provider, max steps, trace và validation URL nguồn.
- `run.py` và `evals/run_evals.py`: tự đọc `.env` với cú pháp `export KEY=value` hoặc `$env:KEY=value`, hỗ trợ cấu hình Gemini.
- Không sửa fixtures, cases, scenarios, grading hoặc rubric.

Validation URL được chọn làm cải tiến: sau khi `get_incident_details` thành công, agent yêu cầu model bổ sung URL nếu final answer thiếu nguồn; không bắt nguồn khi tool thất bại.

## 4. So sánh hai lần chạy

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---:|---:|
| Điểm tổng | null (15/22 unscored) | null (14/22 unscored) |
| Case đã chọn | E1/E2: 100; H7: 50 | E1/E2: 100; H7 chưa chạy do rate limit |
| Số model calls | Có trong từng case/usage | Có trong từng case/usage |
| Token, chi phí | Có usage từng case; không có giá trong report | Có usage từng case; không có giá trong report |

## 5. Giới hạn

- Gemini rate limit làm điểm tổng không hợp lệ; partial mean chỉ tham khảo.
- Snapshot chỉ phản ánh dữ liệu được ghi ngày 09/11/2026, không phải trạng thái live.
- Judge LLM là ước lượng; một lần chạy không chứng minh độ ổn định.
- Free/rate-limited provider cần chạy lại sau khi quota reset hoặc dùng model/quota phù hợp.

CP6 dùng đúng config CP4: Gemini `models/gemini-flash-lite-latest`, judge cùng model, `max_steps=8`, `workers=1`. Kết quả: 8/22 scored, 14/22 unscored do rate limit; `partial_mean_0_100` là 100.0 nhưng không phải điểm cuối.
