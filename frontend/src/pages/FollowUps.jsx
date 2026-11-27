import { useState } from "react";
import { api } from "../api/client";
import FollowUpCard from "../components/FollowUpCard";
import { AsyncBoundary, EmptyState, Pagination } from "../components/ui";
import { useAsync } from "../hooks/useAsync";

const GROUPS = [
  { value: "pending", label: "Needs action" },
  { value: "completed", label: "Done" },
  { value: "rejected", label: "Rejected" },
  { value: "all", label: "All" },
];

export default function FollowUps() {
  const [group, setGroup] = useState("pending");
  const [priority, setPriority] = useState("");
  const [page, setPage] = useState(1);
  const list = useAsync(() => api.followUps({ group, priority, page, page_size: 10 }), [group, priority, page]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Follow-ups</h1>
        <p className="text-sm text-slate-500">AI drafts messages; a person reviews and approves every one. Nothing is sent automatically.</p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {GROUPS.map((g) => (
          <button
            key={g.value}
            onClick={() => { setGroup(g.value); setPage(1); }}
            className={`rounded-full px-4 py-1.5 text-sm font-medium ${group === g.value ? "bg-brand-600 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"}`}
          >
            {g.label}
          </button>
        ))}
        <select className="input ml-auto w-40" value={priority} onChange={(e) => { setPriority(e.target.value); setPage(1); }} aria-label="Priority">
          <option value="">Any priority</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      <AsyncBoundary state={list}>
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState title="Nothing here" hint={group === "pending" ? "Open a lead and use “Suggest follow-up” to generate a draft." : undefined} />
          ) : (
            <>
              <div className="space-y-4">
                {data.items.map((f) => (
                  <FollowUpCard key={f.id} followUp={f} onChanged={list.reload} />
                ))}
              </div>
              <Pagination page={data.page} pageSize={data.page_size} total={data.total} onChange={setPage} />
            </>
          )
        }
      </AsyncBoundary>
    </div>
  );
}
