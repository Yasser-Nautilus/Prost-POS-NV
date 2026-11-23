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
