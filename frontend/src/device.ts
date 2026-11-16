import { useEffect, useState } from "react";

export type Device = "phone" | "tablet" | "desktop";
export type DeviceChoice = Device | "auto";

const KEY = "hani2-device";

export function getDeviceChoice(): DeviceChoice {
  const q = new URLSearchParams(location.search).get("device");
  if (q === "phone" || q === "tablet" || q === "desktop") return q;
  try {
    const v = localStorage.getItem(KEY);
    if (v === "phone" || v === "tablet" || v === "desktop") return v;
  } catch {
    /* ignore */
  }
  return "auto";
}

export function setDeviceChoice(v: DeviceChoice) {
  try {
    if (v === "auto") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, v);
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new Event("hani2-device"));
}

function detect(): Device {
  const w = window.innerWidth;
  const coarse = window.matchMedia("(pointer: coarse)").matches;
  if (w < 640) return "phone";
  if (w < 1024) return "tablet";
  if (coarse && w < 1400) return "tablet"; // touch screens up to large tablets
  return "desktop";
}

/** The layout to use, its orientation, and what was detected. */
export function useDevice(): { device: Device; landscape: boolean; choice: DeviceChoice } {
  const read = () => {
    const choice = getDeviceChoice();
    return {
      choice,
      device: choice === "auto" ? detect() : choice,
      landscape: window.innerWidth > window.innerHeight && window.innerWidth >= 900,
    };
  };
  const [v, setV] = useState(read);
  useEffect(() => {
    const on = () => setV(read());
    window.addEventListener("resize", on);
    window.addEventListener("orientationchange", on);
    window.addEventListener("hani2-device", on);
    return () => {
      window.removeEventListener("resize", on);
      window.removeEventListener("orientationchange", on);
      window.removeEventListener("hani2-device", on);
    };
  }, []);
  useEffect(() => {
    document.documentElement.dataset.device = v.device;
  }, [v.device]);
  return v;
}
