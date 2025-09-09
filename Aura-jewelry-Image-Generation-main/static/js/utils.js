// static/js/utils.js — robust shim

// 1) Re-export any named exports if they exist
export * from "./core/utils.js";

// 2) Also import the default (most likely an object of helpers)
import _utilsDefault from "./core/utils.js";

// 3) If named exports were missing in the core file,
//    expose them here so `import { byId } from "../utils.js"` still works.
export const byId             = _utilsDefault?.byId;
export const getValue         = _utilsDefault?.getValue;
export const fillSelect       = _utilsDefault?.fillSelect;
export const convertLabelToId = _utilsDefault?.convertLabelToId;
export const fetchJSON        = _utilsDefault?.fetchJSON;

// 4) Keep default export for callers that use it
export default _utilsDefault;
