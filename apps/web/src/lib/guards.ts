import type { User, UserRole } from "@/types";

/**
 * Check if user has one of the allowed roles.
 * Returns true if user exists and their role is in the allowed list.
 */
export function hasRole(user: User | null | undefined, allowedRoles: UserRole[]): boolean {
  if (!user) return false;
  return allowedRoles.includes(user.role as UserRole);
}

/**
 * Check if user is admin or rop (management roles).
 */
export function isManager(user: User | null | undefined): boolean {
  return hasRole(user, ["admin", "rop"]);
}

/**
 * Check if user is admin.
 */
export function isAdmin(user: User | null | undefined): boolean {
  return hasRole(user, ["admin"]);
}

/**
 * Check if user is rop (team lead). Distinct from `isManager` which
 * confusingly returns true for admin+rop ("management roles") — the
 * literal `manager` user role is the rank-and-file sales manager.
 */
export function isROP(user: User | null | undefined): boolean {
  return hasRole(user, ["rop"]);
}

/**
 * Role display names in Russian.
 *
 * Note: the `methodologist` role was retired 2026-04-26. Stale JWT
 * tokens issued before that date may still claim it; the case branch
 * keeps stale tokens displaying "РОП" (their post-migration role)
 * until the token rolls over on next refresh. Drops in B3.2 with the
 * alias + enum-value cleanup.
 */
export function roleName(role: string): string {
  switch (role) {
    case "admin": return "Администратор";
    case "rop": return "РОП";
    case "methodologist": return "РОП";
    case "manager": return "Менеджер";
    default: return role;
  }
}
