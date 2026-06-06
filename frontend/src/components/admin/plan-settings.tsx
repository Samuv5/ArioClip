"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent } from "@/components/ui/card";

interface PlanLimit {
  key: string;
  label: string;
  value: string;
}

export function PlanSettings() {
  const [limits, setLimits] = useState<PlanLimit[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/admin/plans")
      .then((r) => r.json())
      .then((data) => {
        if (data.limits) setLimits(data.limits);
        else setError("Failed to load plan settings");
      })
      .catch(() => setError("Failed to load plan settings"))
      .finally(() => setLoading(false));
  }, []);

  const handleChange = (key: string, value: string) => {
    setLimits((prev) => prev.map((l) => (l.key === key ? { ...l, value } : l)));
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch("/api/admin/plans", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limits: Object.fromEntries(limits.map((l) => [l.key, l.value])) }),
      });
      if (!res.ok) {
        const data = await res.json();
        setError(data.error || "Failed to save");
      } else {
        setSuccess("Plan limits saved");
      }
    } catch {
      setError("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <p className="text-sm text-muted-foreground">Loading plan settings...</p>;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {limits.map((limit) => (
          <Card key={limit.key} className="border-border">
            <CardContent className="p-4 space-y-2">
              <label className="text-sm font-medium text-foreground">{limit.label}</label>
              <p className="text-xs text-muted-foreground">Generations per billing period (0 = unlimited)</p>
              <Input
                type="number"
                min={0}
                value={limit.value}
                onChange={(e) => handleChange(limit.key, e.target.value)}
                disabled={saving}
              />
            </CardContent>
          </Card>
        ))}
      </div>
      {error && <Alert className="border-red-200 bg-red-50"><AlertDescription className="text-sm text-red-700">{error}</AlertDescription></Alert>}
      {success && <Alert className="border-green-200 bg-green-50"><AlertDescription className="text-sm text-green-700">{success}</AlertDescription></Alert>}
      <Button onClick={handleSave} disabled={saving} size="sm">{saving ? "Saving..." : "Save Limits"}</Button>
    </div>
  );
}
