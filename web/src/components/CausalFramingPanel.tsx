import type { CausalTree } from "@/lib/schema";

type Props = {
  tree: CausalTree;
};

function ListSection({
  title,
  items,
}: {
  title: string;
  items: string[];
}) {
  return (
    <div className="rounded-lg bg-slate-950 p-4">
      <h4 className="font-semibold text-slate-100">{title}</h4>

      {items.length > 0 ? (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-300">
          {items.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-slate-500">None identified.</p>
      )}
    </div>
  );
}

export function CausalFramingPanel({ tree }: Props) {
  const framing = tree.causal_framing;

  return (
    <section className="mt-6 rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-purple-300">
          Causal framing lens
        </p>

        <h3 className="mt-1 text-xl font-semibold text-slate-100">
          What is the article making causality look like?
        </h3>

        <p className="mt-2 text-sm text-slate-300">
          This panel describes how the article supports, implies, or leaves open causal
          explanations; it does not claim the causes are objectively true.
        </p>
      </div>

      <div className="mt-5 rounded-lg border border-purple-900 bg-purple-950 p-4">
        <h4 className="font-semibold text-purple-100">Dominant explanation</h4>
        <p className="mt-2 text-sm text-purple-50">
          {framing.dominant_explanation}
        </p>
      </div>

      <div className="mt-4 rounded-lg border border-slate-700 bg-slate-950 p-4">
        <h4 className="font-semibold text-slate-100">Causal signature</h4>
        <p className="mt-2 font-mono text-sm text-slate-300">
          {framing.causal_signature}
        </p>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <ListSection
          title="Foregrounded causes"
          items={framing.foregrounded_causes}
        />

        <ListSection
          title="Backgrounded causes"
          items={framing.backgrounded_causes}
        />

        <ListSection
          title="Alternative explanations"
          items={framing.alternative_explanations}
        />

        <ListSection
          title="Possible blind spots"
          items={framing.possible_blind_spots}
        />
      </div>
    </section>
  );
}