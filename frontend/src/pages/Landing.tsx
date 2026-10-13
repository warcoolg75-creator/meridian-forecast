import { SiteFooter } from "./landing/SiteFooter";
import { SiteHeader } from "./landing/SiteHeader";
import { Hero, HowItWorks, OurGoals, WhatWeDo } from "./landing/sections";

export default function Landing() {
  return (
    <>
      <SiteHeader />
      <main>
        <Hero />
        <WhatWeDo />
        <HowItWorks />
        <OurGoals />
      </main>
      <SiteFooter />
    </>
  );
}
