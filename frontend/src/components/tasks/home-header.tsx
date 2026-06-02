"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";
import { ThemeToggle } from "@/components/theme-toggle";
import { signOut, useSession } from "@/lib/auth-client";
import { formatBillingPlanName, isPaidBillingPlan } from "@/lib/billing-plans";
import Link from "next/link";
import Image from "next/image";
import {
  List, Shield, Settings, Menu, X, LogOut,
} from "lucide-react";
interface BillingSummary {
  monetization_enabled: boolean;
  plan: string;
  subscription_status: string;
  usage_count: number;
  usage_limit: number | null;
  remaining: number | null;
  can_create_task: boolean;
  upgrade_required: boolean;
  reason: string | null;
}

interface HomeHeaderProps {
  billingSummary: BillingSummary | null;
  isAdmin: boolean;
}

export function HomeHeader({ billingSummary, isAdmin }: HomeHeaderProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { data: session } = useSession();

  if (!session?.user) return null;

  const handleSignOut = async () => {
    await signOut();
    window.location.href = "/sign-in";
  };

  return (
    <div className="border-b border-border bg-background relative">
      <div className="max-w-7xl mx-auto px-4 py-4">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-3">
            <Image
              src="/logo.png"
              alt="SupoClip"
              width={24}
              height={24}
              className="rounded-lg"
            />
            <h1 className="text-xl font-bold text-foreground">SupoClip</h1>
          </div>

          {/* Desktop nav */}
          <div className="hidden md:flex items-center gap-2">
            {billingSummary?.monetization_enabled && (
              <div className="flex items-center gap-2 mr-1">
                <Badge
                  className={`text-[10px] px-1.5 py-0 h-5 ${
                    isPaidBillingPlan(billingSummary.plan) && !billingSummary.upgrade_required
                      ? "bg-primary text-primary-foreground"
                      : "bg-amber-100 text-amber-800 border border-amber-200"
                  }`}
                >
                  {isPaidBillingPlan(billingSummary.plan) && !billingSummary.upgrade_required
                    ? formatBillingPlanName(billingSummary.plan)
                    : "Upgrade required"}
                </Badge>
                {!billingSummary.upgrade_required && (
                <div className="flex items-center gap-1.5">
                  <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        billingSummary.usage_limit &&
                        billingSummary.usage_count / billingSummary.usage_limit > 0.8
                          ? "bg-red-500"
                          : "bg-primary"
                      }`}
                      style={{
                        width: billingSummary.usage_limit
                          ? `${Math.min((billingSummary.usage_count / billingSummary.usage_limit) * 100, 100)}%`
                          : "0%",
                      }}
                    />
                  </div>
                  <span className="text-[11px] text-muted-foreground tabular-nums whitespace-nowrap">
                    {billingSummary.usage_limit
                      ? `${billingSummary.usage_count}/${billingSummary.usage_limit}`
                      : `${billingSummary.usage_count}`}
                  </span>
                </div>
                )}
              </div>
            )}
            <Link href="/list">
              <Button variant="outline" size="sm">All Generations</Button>
            </Link>
            {isAdmin && (
              <Link href="/admin">
                <Button variant="outline" size="sm">Admin</Button>
              </Link>
            )}
            <Link href="/youtube">
              <Button variant="outline" size="sm" className="text-red-600 border-red-200 hover:bg-destructive/10">
                YouTube
              </Button>
            </Link>
            <ThemeToggle />
            <Button variant="outline" size="sm" onClick={handleSignOut}>Sign Out</Button>
            <Link href="/settings" className="flex items-center gap-3 hover:bg-muted/50 rounded-lg px-3 py-2 transition-colors cursor-pointer">
              <Avatar className="w-8 h-8">
                <AvatarImage src={session.user.image || ""} />
                <AvatarFallback className="bg-muted text-foreground text-sm">
                  {session.user.name?.charAt(0) || session.user.email?.charAt(0) || "U"}
                </AvatarFallback>
              </Avatar>
              <div className="hidden sm:block">
                <p className="text-sm font-medium text-foreground">{session.user.name}</p>
                <p className="text-xs text-muted-foreground">{session.user.email}</p>
              </div>
            </Link>
          </div>

          {/* Mobile hamburger */}
          <div className="flex items-center gap-2 md:hidden">
            {billingSummary?.monetization_enabled && (
              <Badge
                className={`text-[10px] px-1.5 py-0 h-5 ${
                  isPaidBillingPlan(billingSummary.plan) && !billingSummary.upgrade_required
                    ? "bg-primary text-primary-foreground"
                    : "bg-amber-100 text-amber-800 border border-amber-200"
                }`}
              >
                {isPaidBillingPlan(billingSummary.plan) && !billingSummary.upgrade_required
                  ? formatBillingPlanName(billingSummary.plan)
                  : "Upgrade required"}
              </Badge>
            )}
            <Button
              variant="ghost" size="sm"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2"
              aria-label="Toggle menu"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </Button>
          </div>
        </div>
      </div>

      {/* Mobile menu dropdown */}
      {mobileMenuOpen && (
        <div className="md:hidden border-t border-border bg-background absolute left-0 right-0 z-50 shadow-lg">
          <div className="px-4 py-3 space-y-1">
            <Link href="/settings" onClick={() => setMobileMenuOpen(false)}
              className="flex items-center gap-3 rounded-lg px-3 py-2.5 hover:bg-muted/50 transition-colors">
              <Avatar className="w-8 h-8">
                <AvatarImage src={session.user.image || ""} />
                <AvatarFallback className="bg-muted text-foreground text-sm">
                  {session.user.name?.charAt(0) || session.user.email?.charAt(0) || "U"}
                </AvatarFallback>
              </Avatar>
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground truncate">{session.user.name}</p>
                <p className="text-xs text-muted-foreground truncate">{session.user.email}</p>
              </div>
            </Link>
            <Separator />

            {billingSummary?.monetization_enabled && (
              billingSummary.upgrade_required ? (
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
                  <p className="text-xs font-medium text-amber-900">Choose a paid plan to process videos.</p>
                </div>
              ) : (
                <div className="flex items-center gap-2 px-3 py-2">
                  <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                    <div className={`h-full rounded-full transition-all duration-500 ${
                      billingSummary.usage_limit && billingSummary.usage_count / billingSummary.usage_limit > 0.8
                        ? "bg-red-500" : "bg-primary"
                    }`}
                    style={{
                      width: billingSummary.usage_limit
                        ? `${Math.min((billingSummary.usage_count / billingSummary.usage_limit) * 100, 100)}%`
                        : "0%",
                    }} />
                  </div>
                  <span className="text-xs text-muted-foreground tabular-nums whitespace-nowrap">
                    {billingSummary.usage_limit
                      ? `${billingSummary.usage_count}/${billingSummary.usage_limit}`
                      : `${billingSummary.usage_count}`}
                  </span>
                </div>
              )
            )}

            <Link href="/list" onClick={() => setMobileMenuOpen(false)}
              className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-muted-foreground hover:bg-muted/50 transition-colors">
              <List className="w-4 h-4 text-muted-foreground" /> All Generations
            </Link>
            {isAdmin && (
              <Link href="/admin" onClick={() => setMobileMenuOpen(false)}
                className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-muted-foreground hover:bg-muted/50 transition-colors">
                <Shield className="w-4 h-4 text-muted-foreground" /> Admin
              </Link>
            )}
            <Link href="/settings" onClick={() => setMobileMenuOpen(false)}
              className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-muted-foreground hover:bg-muted/50 transition-colors">
              <Settings className="w-4 h-4 text-muted-foreground" /> Settings
            </Link>

            <Separator />
            <div className="px-3 py-2"><ThemeToggle /></div>
            <button onClick={() => { setMobileMenuOpen(false); handleSignOut(); }}
              className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-red-600 hover:bg-destructive/10 transition-colors w-full text-left">
              <LogOut className="w-4 h-4" /> Sign Out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
