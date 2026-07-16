"use client";

type Props = {
  data: unknown;
  filename: string;
};

export function ExportJsonButton({ data, filename }: Props) {
  function downloadJson() {
    const json = JSON.stringify(data, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();

    URL.revokeObjectURL(url);
  }

  return (
    <button
      onClick={downloadJson}
      className="rounded-lg border border-slate-700 bg-slate-950 px-4 py-2 text-sm font-medium text-slate-100 hover:bg-slate-800"
    >
      Export causal tree JSON
    </button>
  );
}