/** Saves a file the website received (e.g. an Excel export) to the reviewer's downloads, like a download link. */
export function saveFile(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  // Some browsers start reading the file only after click() returns: release it a while later.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
