import { useEffect, useState } from "react";
import { KeyRound, Shield, Trash2, UserPlus, UserRound } from "lucide-react";
import { api } from "../../api";
import { Group } from "../Group";
import { Row, Tile } from "../Row";
import { TextField } from "../controls/TextField";
import { Toggle } from "../controls/Toggle";
import { toast } from "../toast";

export function Users() {
  const [rows, setRows] = useState<any[]>([]);
  const [n, setN] = useState({ username: "", password: "", email: "", is_admin: false });
  const [q, setQ] = useState("");
  const load = () => api("/api/admin/users").then(setRows);
  useEffect(() => {
    load();
  }, []);
  const add = async () => {
    try {
      await api("/api/admin/users", { body: n });
      toast(`Created ${n.username}`);
      setN({ username: "", password: "", email: "", is_admin: false });
      load();
    } catch (err: any) {
      toast(err.message, "error");
    }
  };
  const shown = rows.filter((u) => !q || `${u.username} ${u.full_name ?? ""} ${u.email ?? ""}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      <Group title="Add a user" footer="Users created here count as having consented." id="setting-add-user">
        <Row id="user-name" label="Username">
          <TextField label="Username" value={n.username} onChange={(v) => setN({ ...n, username: v })} className="w-56" />
        </Row>
        <Row label="Password">
          <TextField label="Password" type="password" value={n.password} onChange={(v) => setN({ ...n, password: v })} className="w-56" />
        </Row>
        <Row label="Email" hint="Optional">
          <TextField label="Email" type="email" value={n.email} onChange={(v) => setN({ ...n, email: v })} className="w-56" />
        </Row>
        <Row id="user-admin" label="Administrator">
          <Toggle label="Administrator" value={n.is_admin} onChange={(v) => setN({ ...n, is_admin: v })} />
        </Row>
        <Row label="">
          <button className="btn-primary" disabled={!n.username || !n.password} onClick={add}>
            <UserPlus size={15} /> Add user
          </button>
        </Row>
      </Group>
      <Group title={`Accounts (${rows.length})`} actions={<TextField label="Filter users" placeholder="Filter" value={q} onChange={setQ} className="w-40" />} id="setting-accounts">
        {shown.map((u) => (
          <Row
            key={u.username}
            icon={<Tile icon={u.is_admin ? Shield : UserRound} color={u.is_admin ? "bg-bad" : "bg-muted"} />}
            label={
              <>
                {u.username} {u.is_admin && <span className="ml-1 rounded bg-bad/10 px-1.5 text-xs text-bad">admin</span>}
              </>
            }
            hint={[u.full_name, u.email, u.oauth && `via ${u.oauth}`, u.consented ? "consented" : "no consent yet"].filter(Boolean).join(" · ")}
          >
            {u.username !== "admin" && (
              <button className="btn-ghost text-xs" onClick={async () => { await api(`/api/admin/users/${encodeURIComponent(u.username)}`, { method: "PATCH", body: { is_admin: !u.is_admin } }); load(); }}>
                {u.is_admin ? "Remove admin" : "Make admin"}
              </button>
            )}
            <button
              className="btn-ghost text-xs"
              onClick={async () => {
                const p = prompt(`New password for ${u.username}`);
                if (p) {
                  await api(`/api/admin/users/${encodeURIComponent(u.username)}`, { method: "PATCH", body: { password: p } });
                  toast("Password changed");
                }
              }}
            >
              <KeyRound size={13} /> Set password
            </button>
            {u.username !== "admin" && (
              <button
                className="btn-ghost px-2 text-bad"
                aria-label={`Delete ${u.username}`}
                onClick={async () => {
                  if (confirm(`Delete ${u.username}? Their results are kept.`)) {
                    await api(`/api/admin/users/${encodeURIComponent(u.username)}`, { method: "DELETE" });
                    load();
                  }
                }}
              >
                <Trash2 size={15} />
              </button>
            )}
          </Row>
        ))}
      </Group>
    </>
  );
}
