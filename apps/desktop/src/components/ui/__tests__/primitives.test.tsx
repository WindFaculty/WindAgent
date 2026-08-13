import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import {
  Button,
  IconButton,
  Badge,
  StatusBadge,
  Panel,
  Card,
  EmptyState,
  SectionHeader,
  Tabs,
  ProgressBar,
  Skeleton,
  Alert,
  Dropdown,
  Tooltip,
  Icon,
} from '../index';

describe('UI Primitives Foundation (UI1.3)', () => {
  afterEach(cleanup);

  it('renders Button with variants, sizes, loading state and handles clicks', () => {
    const handleClick = vi.fn();
    const { rerender } = render(
      <Button variant="primary" size="md" onClick={handleClick}>
        Submit
      </Button>
    );

    const button = screen.getByRole('button', { name: 'Submit' });
    expect(button).toBeInTheDocument();
    expect(button.className).toContain('ui-button--primary');
    expect(button.className).toContain('ui-button--md');

    fireEvent.click(button);
    expect(handleClick).toHaveBeenCalledTimes(1);

    // Test loading state disables button
    rerender(
      <Button variant="danger" isLoading onClick={handleClick}>
        Deleting
      </Button>
    );
    const loadingBtn = screen.getByRole('button');
    expect(loadingBtn).toBeDisabled();
    expect(loadingBtn.className).toContain('ui-button--danger');
  });

  it('renders IconButton with accessibility label', () => {
    const handleClick = vi.fn();
    render(
      <IconButton
        aria-label="Settings Icon"
        icon={<span data-testid="test-icon">⚙</span>}
        onClick={handleClick}
      />
    );

    const iconBtn = screen.getByRole('button', { name: 'Settings Icon' });
    expect(iconBtn).toBeInTheDocument();
    expect(screen.getByTestId('test-icon')).toBeInTheDocument();
  });

  it('renders Badge with default and semantic variants', () => {
    render(
      <>
        <Badge variant="primary">Primary Tag</Badge>
        <Badge variant="success">Success Tag</Badge>
      </>
    );

    expect(screen.getByText('Primary Tag').className).toContain('ui-badge--primary');
    expect(screen.getByText('Success Tag').className).toContain('ui-badge--success');
  });

  it('renders StatusBadge mapping Studio statuses to appropriate styling', () => {
    const { rerender } = render(<StatusBadge status="RUNNING" />);
    expect(screen.getByText('RUNNING')).toBeInTheDocument();

    rerender(<StatusBadge status="LOCKED" />);
    expect(screen.getByText('LOCKED').className).toContain('ui-badge--accent');

    rerender(<StatusBadge status="FAILED" />);
    expect(screen.getByText('FAILED').className).toContain('ui-badge--danger');
  });

  it('renders Panel with header, content, and footer', () => {
    render(
      <Panel header={<div>Panel Title</div>} footer={<div>Panel Footer</div>}>
        <div>Panel Body</div>
      </Panel>
    );

    expect(screen.getByText('Panel Title')).toBeInTheDocument();
    expect(screen.getByText('Panel Body')).toBeInTheDocument();
    expect(screen.getByText('Panel Footer')).toBeInTheDocument();
  });

  it('renders Card with interactive hover class when specified', () => {
    const { rerender } = render(<Card>Static Card</Card>);
    expect(screen.getByText('Static Card').className).not.toContain('ui-card--interactive');

    rerender(<Card interactive>Interactive Card</Card>);
    expect(screen.getByText('Interactive Card').className).toContain('ui-card--interactive');
  });

  it('renders EmptyState with icon, title, description, and action', () => {
    render(
      <EmptyState
        title="No Series Available"
        description="Create your first series to get started."
        action={<Button>Create Series</Button>}
      />
    );

    expect(screen.getByText('No Series Available')).toBeInTheDocument();
    expect(screen.getByText('Create your first series to get started.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create Series' })).toBeInTheDocument();
  });

  it('renders SectionHeader with title, subtitle and action slot', () => {
    render(
      <SectionHeader
        title="Episodes"
        subtitle="Manage episode sequence"
        action={<Button size="sm">Add Episode</Button>}
      />
    );

    expect(screen.getByText('Episodes')).toBeInTheDocument();
    expect(screen.getByText('Manage episode sequence')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add Episode' })).toBeInTheDocument();
  });

  it('renders Tabs and handles tab switching', () => {
    const handleTabChange = vi.fn();
    const tabs = [
      { id: 'overview', label: 'Overview' },
      { id: 'screenplay', label: 'Screenplay' },
    ];

    render(<Tabs tabs={tabs} activeTab="overview" onChange={handleTabChange} />);

    const screenplayTab = screen.getByRole('tab', { name: 'Screenplay' });
    expect(screenplayTab).toHaveAttribute('data-active', 'false');

    const overviewTab = screen.getByRole('tab', { name: 'Overview' });
    expect(overviewTab).toHaveAttribute('data-active', 'true');

    fireEvent.click(screenplayTab);
    expect(handleTabChange).toHaveBeenCalledWith('screenplay');
  });

  it('renders ProgressBar in determinate and indeterminate modes', () => {
    const { rerender } = render(<ProgressBar value={45} data-testid="progress-bar" />);
    const bar = screen.getByTestId('progress-bar');
    expect(bar).toHaveAttribute('aria-valuenow', '45');

    rerender(<ProgressBar indeterminate data-testid="progress-bar" />);
    expect(bar).not.toHaveAttribute('aria-valuenow');
  });

  it('renders Skeleton loading placeholder', () => {
    render(<Skeleton data-testid="skeleton" width={100} height={20} />);
    const skeleton = screen.getByTestId('skeleton');
    expect(skeleton.className).toContain('ui-skeleton');
  });

  it('renders Alert component with semantic types', () => {
    render(
      <Alert type="warning" title="Warning Header">
        Caution required
      </Alert>
    );

    expect(screen.getByText('Warning Header')).toBeInTheDocument();
    expect(screen.getByText('Caution required')).toBeInTheDocument();
  });

  it('renders Dropdown select component', () => {
    const handleChange = vi.fn();
    const options = [
      { value: 'v1', label: 'Option 1' },
      { value: 'v2', label: 'Option 2' },
    ];

    render(<Dropdown options={options} value="v1" onChange={handleChange} />);

    const select = screen.getByRole('combobox');
    expect(select).toHaveValue('v1');

    fireEvent.change(select, { target: { value: 'v2' } });
    expect(handleChange).toHaveBeenCalledWith('v2');
  });

  it('renders Tooltip on hover', () => {
    render(
      <Tooltip content="Tooltip Hint">
        <button>Hover Me</button>
      </Tooltip>
    );

    const btn = screen.getByRole('button', { name: 'Hover Me' });
    expect(screen.queryByText('Tooltip Hint')).not.toBeInTheDocument();

    fireEvent.mouseEnter(btn);
    expect(screen.getByText('Tooltip Hint')).toBeInTheDocument();

    fireEvent.mouseLeave(btn);
    expect(screen.queryByText('Tooltip Hint')).not.toBeInTheDocument();
  });

  it('renders Icon authority component', () => {
    render(<Icon name="play" data-testid="icon-play" />);
    expect(screen.getByTestId('icon-play')).toBeInTheDocument();
  });
});
