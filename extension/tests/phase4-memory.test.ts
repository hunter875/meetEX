import {describe,it,expect} from 'vitest';
import {memoryCurrent} from '../src/ui/memory';
describe('Memory current versus evidence-linked history',()=>{
  it('shows the cancellation tombstone, hides the earlier item cancelled by it',()=>{
    expect(memoryCurrent({status:'cancelled',relations:[]})).toBe(true);
    expect(memoryCurrent({status:'cancelled',relations:[{type:'cancelled_by',item_id:'latest'}]})).toBe(false);
    expect(memoryCurrent({status:'confirmed',relations:[{type:'superseded_by',item_id:'latest'}]})).toBe(false);
  });
  it('keeps disputes visible, hides invalidated evidence and accepted proposal history',()=>{
    expect(memoryCurrent({status:'disputed',relations:[{type:'disputes',item_id:'other'}]})).toBe(true);
    expect(memoryCurrent({status:'invalidated',relations:[]})).toBe(false);
    expect(memoryCurrent({status:'accepted',relations:[{type:'accepted_by',item_id:'decision'}]})).toBe(false);
  });
});
