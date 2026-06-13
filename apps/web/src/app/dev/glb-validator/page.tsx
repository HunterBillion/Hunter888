/**
 * Public dev tool — drag-and-drop validator for artist-delivered GLB avatars.
 *
 * No auth (the artist is external). Will be locked behind admin role before
 * pilot launch — see the TODO in GlbValidator.tsx.
 *
 * URL: /dev/glb-validator
 */

import { GlbValidator } from "./GlbValidator";

export const metadata = {
  title: "GLB Validator — Hunter888",
  robots: { index: false, follow: false },
};

export default function Page() {
  return <GlbValidator />;
}
