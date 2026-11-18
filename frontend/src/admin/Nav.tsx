import { createContext, useContext } from "react";

export interface SubPage {
  title: string;
  render: () => React.ReactNode;
}

/** Sub-page navigation inside one settings page (disclosure rows push, the back button pops). */
export const NavContext = createContext<{ push: (p: SubPage) => void; pop: () => void; depth: number }>({ push: () => {}, pop: () => {}, depth: 0 });
export const useNav = () => useContext(NavContext);
