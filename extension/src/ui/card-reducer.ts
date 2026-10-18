import type {Suggestion} from './types';
export type ReadingState={current:Suggestion|null;pending:Suggestion|null;pinned:boolean;seen:string[];manualRequest:string|null};
export const emptyReading:ReadingState={current:null,pending:null,pinned:false,seen:[],manualRequest:null};
type Action={type:'offer';suggestion:Suggestion}|{type:'pin'}|{type:'next'}|{type:'manual';request_id:string}|{type:'restore';state:ReadingState};
export function readingReducer(state:ReadingState,action:Action):ReadingState{
  if(action.type==='restore')return action.state;
  if(action.type==='pin')return {...state,pinned:!state.pinned};
  if(action.type==='next')return {...state,current:state.pending||state.current,pending:null,pinned:false};
  if(action.type==='manual')return {...state,manualRequest:action.request_id};
  const suggestion=action.suggestion;
  if(suggestion.request_id===state.manualRequest)return {...state,current:suggestion,manualRequest:null,seen:state.seen.includes(suggestion.id)?state.seen:[...state.seen,suggestion.id]};
  if(state.seen.includes(suggestion.id))return state;
  const next={...state,seen:[...state.seen,suggestion.id].slice(-500)};
  if(suggestion.stale)return next;
  if(state.pinned)return {...next,pending:suggestion};
  return {...next,current:suggestion,pending:null};
}
