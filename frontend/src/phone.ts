// Egyptian mobile number helpers. Mirrors broast_pos/core/phone.py.
// Pasted WhatsApp formats (+20, spaces, dashes) are normalised to 01XXXXXXXXX
// written with English digits only.

const MOBILE = /^01[0125][0-9]{8}$/;
const SEPARATORS = /[\s\-().\u200e\u200f\u202a\u202b\u202c\u00a0]/g;

export const INVALID_PHONE_MSG = "رقم الهاتف يجب أن يكون 11 رقم ويبدأ بـ 010 أو 011 أو 012 أو 015";

export function normalizeEgyptianMobile(raw: string | null | undefined): string | null {
  if (!raw) return null;
  let s = raw.replace(SEPARATORS, "");
  if (!s) return null;
  if (s.startsWith("+")) {
    s = s.slice(1);
    if (!s.startsWith("20")) return null;
    s = s.slice(2);
    if (s.length === 10 && s[0] === "1") s = "0" + s;
  } else if (s.startsWith("0020")) {
    s = s.slice(4);
    if (s.length === 10 && s[0] === "1") s = "0" + s;
  } else if (s.startsWith("20") && s.length === 12) {
    s = "0" + s.slice(2);
  }
  return MOBILE.test(s) ? s : null;
}

/** True when the text looks like a phone being typed (digits, +, spaces, dashes only). */
export function looksLikePhone(text: string): boolean {
  return /^[+\d\s\-().]+$/.test(text.trim()) && text.trim().length > 0;
}

/**
 * Stops digit input at the Egyptian mobile length (11) so a wrong number is
 * obvious without counting. Text that contains letters (a name search) is
 * left alone, and pasted international forms (+20..., 0020..., 20...) keep
 * the extra length they legitimately need.
 */
export function capPhoneInput(raw: string): string {
  if (/[^\d+\s\-().\u200e\u200f\u202a\u202b\u202c\u00a0]/.test(raw)) return raw;
  const compact = raw.replace(SEPARATORS, "");
  let max = 11;
  if (compact.startsWith("+")) max = 13;
  else if (compact.startsWith("0020")) max = 14;
  else if (compact.startsWith("20")) max = 12;
  if (compact.length <= max) return raw;
  return compact.slice(0, max);
}
