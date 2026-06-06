"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription } from "@/components/ui/alert";

export function CreateUserForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setLoading(true);

    try {
      const res = await fetch("/api/admin/users/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Failed to create user");
      } else {
        setSuccess(`User ${data.user?.email || email} created successfully`);
        setName("");
        setEmail("");
        setPassword("");
      }
    } catch {
      setError("Failed to create user");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <h3 className="text-sm font-medium text-foreground">Create User</h3>
      <div className="grid grid-cols-3 gap-3">
        <Input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required disabled={loading} />
        <Input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required disabled={loading} />
        <Input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required disabled={loading} minLength={6} />
      </div>
      {error && <Alert className="border-red-200 bg-red-50"><AlertDescription className="text-sm text-red-700">{error}</AlertDescription></Alert>}
      {success && <Alert className="border-green-200 bg-green-50"><AlertDescription className="text-sm text-green-700">{success}</AlertDescription></Alert>}
      <Button type="submit" disabled={loading} size="sm">{loading ? "Creating..." : "Create User"}</Button>
    </form>
  );
}
