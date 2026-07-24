import { NextRequest, NextResponse } from "next/server";
import { decideDashboardAccess } from "@/lib/auth";

export function proxy(request: NextRequest) {
  const decision = decideDashboardAccess(request.headers.get("authorization"));

  if (decision === "allow") return NextResponse.next();

  if (decision === "misconfigured") {
    return new NextResponse(
      "NicheScope is locked because production dashboard credentials are not configured.",
      { status: 503 },
    );
  }

  return new NextResponse("Authentication required", {
    status: 401,
    headers: {
      "WWW-Authenticate": 'Basic realm="NicheScope", charset="UTF-8"',
      "Cache-Control": "no-store",
    },
  });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
