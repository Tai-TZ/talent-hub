const IP_CHARS = /^[0-9A-Fa-f:.]{2,45}$/;

/**
 * IP thật của người dùng từ X-Forwarded-For, đếm từ phải sang theo số proxy tin cậy đứng trước Next.
 *
 * Next chỉ tự điền X-Forwarded-For khi request chưa có header này, nên mục ngoài cùng bên trái luôn do client
 * tự đặt. Proxy tin cậy (load balancer) nối IP nó nhìn thấy vào cuối danh sách, vì vậy mục thứ `hops` tính từ
 * phải mới là IP thật. Lấy mục bên trái sẽ cho phép kẻ tấn công đổi IP tuỳ ý để né giới hạn đăng nhập.
 */
export function clientIpFrom(forwardedFor: string | null | undefined, trustedHops: number): string | null {
  const entries = (forwardedFor ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (entries.length === 0) return null;
  const hops = Math.max(1, Math.floor(trustedHops) || 1);
  const ip = entries[Math.max(0, entries.length - hops)] ?? "";
  return IP_CHARS.test(ip) ? ip : null;
}
