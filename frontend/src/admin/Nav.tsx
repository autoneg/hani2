import { createContext, useContext } from "react";

export interface SubPage {
  title: string;
  render: () => React.ReactNode;
  /** stays mounted (hidden) while deeper pages are open, so Back finds it as it was (e.g. a set's
   *  unsaved entries); other pages are rendered afresh on Back, refetching what they show */
  keep?: boolean;
}

/** Sub-page navigation inside one settings page (disclosure rows push, the back button pops). */
export const NavContext = createContext<{ push: (p: SubPage) => void; pop: () => void; depth: number }>({ push: () => {}, pop: () => {}, depth: 0 });
export const useNav = () => useContext(NavContext);
