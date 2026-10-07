"use client";

import { useCallback, useEffect, useState } from "react";
import Modal from "./Modal";
import { ApiError, addMember, createTeam, listMembers, listTeams, removeMember } from "@/lib/api";
import type { Member, Team, User } from "@/lib/types";

const inputClass = "rounded-lg border border-slate-300 px-3 py-1.5 text-sm outline-none focus:border-brand-500";

function TeamCard({ team, user, onChanged }: { team: Team; user: User; onChanged: () => void }) {
  const [members, setMembers] = useState<Member[] | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [error, setError] = useState<string | null>(null);
  const isAdmin = team.role === "admin";

  const load = useCallback(() => {
    listMembers(team.id).then(setMembers).catch((e: Error) => setError(e.message));
  }, [team.id]);

  useEffect(load, [load]);

  async function act(work: () => Promise<unknown>) {
    setError(null);
    try {
      await work();
      load();
      onChanged();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "That did not work.");
    }
  }

  return (
    <li className="rounded-xl border border-slate-200 p-3">
      <div className="flex items-center justify-between">
        <p className="font-medium text-slate-900">{team.name}</p>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">you are {team.role}</span>
      </div>
      <ul className="mt-2 space-y-1">
        {(members ?? []).map((m) => (
          <li key={m.user_id} className="flex items-center justify-between text-sm text-slate-700">
            <span>
              {m.name} <span className="text-slate-500">({m.email}, {m.role})</span>
            </span>
            {(isAdmin || m.user_id === user.id) && (
              <button onClick={() => act(() => removeMember(team.id, m.user_id))} className="text-xs font-medium text-rose-600 hover:underline">
                {m.user_id === user.id ? "Leave" : "Remove"}
              </button>
            )}
          </li>
        ))}
      </ul>
      {isAdmin && (
        <form
          className="mt-3 flex flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            act(async () => {
              await addMember(team.id, email, role);
              setEmail("");
            });
          }}
        >
          <input aria-label="Member email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="teammate@company.com" className={`${inputClass} flex-1`} />
          <select aria-label="Role" value={role} onChange={(e) => setRole(e.target.value)} className={inputClass}>
            <option value="member">member (can edit)</option>
            <option value="viewer">viewer (read only)</option>
            <option value="admin">admin</option>
          </select>
          <button type="submit" disabled={!email.trim()} className="rounded-lg bg-slate-800 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40">
            Add
          </button>
        </form>
      )}
      {error && (
        <p role="alert" className="mt-2 text-sm text-rose-700">
          {error}
        </p>
      )}
    </li>
  );
}

export default function TeamsDialog({ user, onClose, onChanged }: { user: User; onClose: () => void; onChanged: () => void }) {
  const [teams, setTeams] = useState<Team[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    listTeams().then(setTeams).catch((e: Error) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await createTeam(name);
      setName("");
      load();
      onChanged();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not create the team.");
    }
  }

  return (
    <Modal title="Teams" onClose={onClose} wide>
      <p className="text-sm text-slate-600">Move a workspace into a team to share it. Members can edit, viewers can only read. People must have an account before you can add them.</p>
      <form onSubmit={create} className="mt-3 flex gap-2">
        <input aria-label="New team name" value={name} onChange={(e) => setName(e.target.value)} placeholder="New team name" maxLength={80} className={`${inputClass} flex-1`} />
        <button type="submit" disabled={!name.trim()} className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40">
          Create team
        </button>
      </form>
      {error && (
        <p role="alert" className="mt-2 text-sm text-rose-700">
          {error}
        </p>
      )}
      <ul className="mt-4 space-y-3">
        {teams.map((team) => (
          <TeamCard key={team.id} team={team} user={user} onChanged={onChanged} />
        ))}
        {teams.length === 0 && <li className="text-sm text-slate-500">You are not in any team yet.</li>}
      </ul>
    </Modal>
  );
}
