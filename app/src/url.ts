/** 서버 주소 다루기 (순수 함수, 테스트 대상). */

export function normalizeBaseUrl(raw: string | undefined): string | null {
  const trimmed = (raw ?? "").trim().replace(/\/+$/, "");
  if (!/^https?:\/\/[^\s/]+(:\d+)?(\/[^\s]*)?$/.test(trimmed)) {
    return null;
  }
  return trimmed;
}

export function joinUrl(baseUrl: string, path: string): string {
  if (/^https?:\/\//.test(path)) {
    return path;
  }
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${baseUrl}${cleanPath}`;
}

export function audioFileName(uri: string): string {
  const match = /\.([a-z0-9]{2,4})(?:\?.*)?$/i.exec(uri);
  const extension = match ? match[1].toLowerCase() : "m4a";
  return `voice.${extension}`;
}

export function audioMimeType(fileName: string): string {
  const extension = fileName.split(".").pop() ?? "";
  const types: Record<string, string> = {
    m4a: "audio/mp4",
    mp4: "audio/mp4",
    aac: "audio/aac",
    wav: "audio/wav",
    caf: "audio/x-caf",
    "3gp": "audio/3gpp",
    webm: "audio/webm",
  };
  return types[extension] ?? "application/octet-stream";
}
