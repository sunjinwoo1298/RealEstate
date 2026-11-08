import { redirect } from "next/navigation";

export default function CustomerRegisterRedirectPage() {
  // Customer registration now exists at /customer/signup (Feature 10);
  // this route is kept only so old/bookmarked links still land somewhere.
  redirect("/customer/signup");
}
