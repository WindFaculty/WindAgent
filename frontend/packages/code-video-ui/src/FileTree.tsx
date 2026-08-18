import React from 'react';
import { FileTreeItem } from './types';

export interface FileTreeProps {
  rootName: string;
  items: FileTreeItem[];
  activePath: string;
  onSelectFile?: (path: string) => void;
}

export const FileTree: React.FC<FileTreeProps> = ({
  rootName,
  items,
  activePath,
  onSelectFile,
}) => {
  const renderItem = (item: FileTreeItem, depth = 0) => {
    const isSelected = item.path === activePath;
    return (
      <React.Fragment key={item.path}>
        <div
          className={`tree-item ${isSelected ? 'active' : ''}`}
          style={{ paddingLeft: `${depth * 16 + 12}px` }}
          onClick={() => !item.is_dir && onSelectFile?.(item.path)}
        >
          <span className="tree-icon">{item.is_dir ? '📁' : '📄'}</span>
          <span className="tree-label">{item.name}</span>
        </div>
        {item.is_dir &&
          item.children?.map((child) => renderItem(child, depth + 1))}
      </React.Fragment>
    );
  };

  return (
    <div className="file-tree-container">
      <div className="tree-header">
        <span className="tree-root-label">EXPLORER: {rootName}</span>
      </div>
      <div className="tree-body">{items.map((it) => renderItem(it, 0))}</div>
    </div>
  );
};
