/** 파일 올리기(XMLHttpRequest) 응답을 읽는다 (순수 함수, 테스트 대상).
 *
 * Expo 58 의 전역 fetch 는 React Native FormData 의 {uri,name,type} 파일을 보내지 못한다
 * ("Unsupported FormDataPart implementation", 2026-11-06 실기기). 그래서 파일은 React Native 가
 * 원래 지원하는 XMLHttpRequest 로 올리고, 응답은 fetch 쪽(request)과 같은 모양으로 읽는다.
 */

export type UploadResult =
  | { ok: true; body: unknown }
  | { ok: false; status: number; message: string };

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/** status 0 은 연결 자체가 안 된 것(서버 꺼짐·주소 틀림). 2xx 가 아니면 서버의 detail 을 붙인다. */
export function readUploadResult(status: number, responseText: string): UploadResult {
  if (status === 0) {
    return { ok: false, status, message: "서버에 연결하지 못했어요. 서버가 켜져 있는지, 주소가 맞는지 확인하세요." };
  }
  const body = parseJson(responseText);
  if (status >= 200 && status < 300) return { ok: true, body };
  const detail = typeof body === "object" && body !== null && "detail" in body ? String(body.detail) : "";
  return { ok: false, status, message: `서버 오류 ${status} ${detail}`.trim() };
}
