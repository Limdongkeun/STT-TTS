/** 클라우드 L4 Qwen 한국어판을 폰에서 바로 부르기(2026-11-20 사용자 결정: 맥을 거치지 않아야 속도를 제대로 비교한다).
 *
 * 앱에서 STT '클라우드 Qwen 한국어'(qwen3-asr-ko-cloud)를 고르면 녹음을 클라우드 /stt 로 바로 보낸다(머리 X-Stt-Key).
 * 클라우드 서버 안에서는 엔진 이름이 qwen3-asr-ko 라서 보낼 때 바꾸고, 받은 답은 다시 cloud 이름으로 돌려 기록이 맞게 한다.
 * 주소(https 만)나 열쇠가 없으면 null → 지금처럼 맥 서버를 거쳐 간다.
 * 열쇠는 app/.env(깃에 안 올라감)의 EXPO_PUBLIC_STT_CLOUD_KEY. 앱 묶음에 들어가므로 내부 시험 앱에만 쓴다.
 * 다른 파일을 불러오지 않는다(node --test 로 바로 시험한다).
 */

export const CLOUD_STT_ENGINE = "qwen3-asr-ko-cloud";
const CLOUD_SERVER_ENGINE = "qwen3-asr-ko";

export type DirectSttTarget = { url: string; headers: Record<string, string>; fields: Record<string, string> };

export function directCloudTarget(
  engine: string | undefined, cloudUrl: string | undefined, cloudKey: string | undefined,
): DirectSttTarget | null {
  if (engine !== CLOUD_STT_ENGINE) return null;
  const base = httpsBase(cloudUrl);
  const key = (cloudKey ?? "").trim();
  if (!base || !key) return null;
  return { url: `${base}/stt`, headers: { "X-Stt-Key": key }, fields: { engine: CLOUD_SERVER_ENGINE } };
}

/** 열쇠를 실어 보내므로 https 주소만. 끝 빗금은 뗀다. 아니면 null. */
function httpsBase(raw: string | undefined): string | null {
  const value = (raw ?? "").trim().replace(/\/+$/, "");
  if (!value.startsWith("https://")) return null;
  try {
    return new URL(value).host ? value : null;
  } catch {
    return null;
  }
}

/** 클라우드가 돌려준 엔진 이름(qwen3-asr-ko)을 앱에서 고른 이름으로 되돌린다. */
export function asCloudReply<T extends { engine: string }>(reply: T): T {
  return { ...reply, engine: CLOUD_STT_ENGINE };
}
