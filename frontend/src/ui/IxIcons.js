import React from 'react';
import { IxIcon } from '@siemens/ix-react';
import { ixIconName } from './ixIconRegistry';

const iconMap = {
  AlertTriangle: ixIconName.warning,
  BarChart2: ixIconName.gauge,
  BarChart3: ixIconName.gauge,
  BookOpen: ixIconName.documentInfo,
  Boxes: ixIconName.database,
  Bot: ixIconName.networkDevice,
  Check: ixIconName.check,
  CheckCircle: ixIconName.check,
  CheckCircle2: ixIconName.check,
  Database: ixIconName.database,
  DatabaseZap: ixIconName.database,
  Download: ixIconName.download,
  Eye: ixIconName.eye,
  Factory: ixIconName.factoryReset,
  FileCode2: ixIconName.documentInfo,
  FileInput: ixIconName.upload,
  Gauge: ixIconName.gauge,
  GitMerge: ixIconName.networkDevice,
  Info: ixIconName.info,
  Link2: ixIconName.networkDevice,
  Loader2: ixIconName.refreshSettings,
  Minus: ixIconName.minus,
  Network: ixIconName.networkDevice,
  Play: ixIconName.play,
  PanelsTopLeft: ixIconName.gauge,
  RefreshCw: ixIconName.refreshSettings,
  Search: ixIconName.search,
  Settings: ixIconName.refreshSettings,
  ShieldCheck: ixIconName.shieldCheck,
  Tags: ixIconName.tagEye,
  Target: ixIconName.tagEye,
  Trash2: ixIconName.minus,
  Upload: ixIconName.upload,
  Workflow: ixIconName.networkDevice,
  X: ixIconName.close,
  Zap: ixIconName.gauge,
};

function createIxIcon(name) {
  const Icon = ({ size = 16, ...props }) => (
    <IxIcon name={iconMap[name]} size={String(size)} {...props} />
  );
  Icon.displayName = `Ix${name}`;
  return Icon;
}

export const AlertTriangle = createIxIcon('AlertTriangle');
export const BarChart2 = createIxIcon('BarChart2');
export const BarChart3 = createIxIcon('BarChart3');
export const BookOpen = createIxIcon('BookOpen');
export const Boxes = createIxIcon('Boxes');
export const Bot = createIxIcon('Bot');
export const Check = createIxIcon('Check');
export const CheckCircle = createIxIcon('CheckCircle');
export const CheckCircle2 = createIxIcon('CheckCircle2');
export const Database = createIxIcon('Database');
export const DatabaseZap = createIxIcon('DatabaseZap');
export const Download = createIxIcon('Download');
export const Eye = createIxIcon('Eye');
export const Factory = createIxIcon('Factory');
export const FileCode2 = createIxIcon('FileCode2');
export const FileInput = createIxIcon('FileInput');
export const Gauge = createIxIcon('Gauge');
export const GitMerge = createIxIcon('GitMerge');
export const Info = createIxIcon('Info');
export const Link2 = createIxIcon('Link2');
export const Loader2 = createIxIcon('Loader2');
export const Minus = createIxIcon('Minus');
export const Network = createIxIcon('Network');
export const Play = createIxIcon('Play');
export const PanelsTopLeft = createIxIcon('PanelsTopLeft');
export const RefreshCw = createIxIcon('RefreshCw');
export const Search = createIxIcon('Search');
export const Settings = createIxIcon('Settings');
export const ShieldCheck = createIxIcon('ShieldCheck');
export const Tags = createIxIcon('Tags');
export const Target = createIxIcon('Target');
export const Trash2 = createIxIcon('Trash2');
export const Upload = createIxIcon('Upload');
export const Workflow = createIxIcon('Workflow');
export const Zap = createIxIcon('Zap');
export const X = createIxIcon('X');
