import React from 'react';
import {MotifProps} from '../types';
import {placeholder} from './Placeholder';
import {Kaumudi} from './Kaumudi';
import {Chakora} from './Chakora';
import {Mandala} from './Mandala';
import {Mana} from './Mana';
import {Madana} from './Madana';
import {Lotus} from './Lotus';

/** motif id (poem.json "motif") -> scene component */
export const MOTIFS: Record<string, React.FC<MotifProps>> = {
  kaumudi: Kaumudi,
  chakora: Chakora,
  mandala: Mandala,
  mana: Mana,
  madana: Madana,
  lotus: Lotus,
};

export const motifFor = (id: string) => MOTIFS[id] ?? placeholder(id);
