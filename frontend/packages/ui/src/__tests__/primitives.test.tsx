import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import * as matchers from '@testing-library/jest-dom/matchers';
expect.extend(matchers);
import React from 'react';



import {
  Button,
  IconButton,
  Badge,
  StatusBadge,
  Card,
  Panel,
  EmptyState,
  Tabs,
  ProgressBar,
  Skeleton,
  Alert,
  Dropdown,
  Tooltip,
  Input,
  Textarea,
  Select,
  Checkbox,
  Switch,
  Modal,
  Spinner,
  Table,
  SectionHeader,
  PageHeader,
  Stack,
  Grid,
} from '../index';

describe('@windagent/ui Primitive Components', () => {
  afterEach(() => {
    cleanup();
  });
  describe('Button & IconButton', () => {
    it('renders button with children and handles clicks', () => {
      const handleClick = vi.fn();
      render(<Button onClick={handleClick}>Click Me</Button>);
      const btn = screen.getByRole('button', { name: 'Click Me' });
      expect(btn).toBeInTheDocument();
      fireEvent.click(btn);
      expect(handleClick).toHaveBeenCalledTimes(1);
    });

    it('renders variants and sizes correctly', () => {
      render(
        <Button variant="danger" size="lg">
          Delete
        </Button>
      );
      const btn = screen.getByRole('button', { name: 'Delete' });
      expect(btn.className).toContain('ui-button--danger');
      expect(btn.className).toContain('ui-button--lg');
    });

    it('disables button when disabled or loading', () => {
      render(<Button isLoading>Saving</Button>);
      const btn = screen.getByRole('button');
      expect(btn).toBeDisabled();
      expect(btn).toHaveAttribute('aria-busy', 'true');
    });

    it('renders IconButton with required aria-label', () => {
      const handleClick = vi.fn();
      render(
        <IconButton
          icon={<span data-testid="icon">🔍</span>}
          aria-label="Search items"
          onClick={handleClick}
        />
      );
      const btn = screen.getByRole('button', { name: 'Search items' });
      expect(btn).toBeInTheDocument();
      expect(screen.getByTestId('icon')).toBeInTheDocument();
      fireEvent.click(btn);
      expect(handleClick).toHaveBeenCalledTimes(1);
    });
  });

  describe('Badge & StatusBadge', () => {
    it('renders Badge with text and variant', () => {
      render(<Badge variant="primary">New Feature</Badge>);
      expect(screen.getByText('New Feature')).toBeInTheDocument();
    });

    it('renders StatusBadge with status mappings and role', () => {
      render(<StatusBadge status="RUNNING" />);
      const badge = screen.getByRole('status');
      expect(badge).toHaveTextContent('RUNNING');
      expect(badge.className).toContain('ui-badge--primary');
    });

    it('renders StatusBadge for SUCCESS status', () => {
      render(<StatusBadge status="SUCCESS" />);
      const badge = screen.getByRole('status');
      expect(badge.className).toContain('ui-badge--success');
    });
  });

  describe('Card & Panel', () => {
    it('renders Card and handles keyboard interaction when interactive', () => {
      const handleClick = vi.fn();
      render(
        <Card interactive onClick={handleClick} data-testid="card">
          Card Content
        </Card>
      );
      const card = screen.getByTestId('card');
      expect(card.className).toContain('ui-card--interactive');
      expect(card).toHaveAttribute('tabindex', '0');

      fireEvent.keyDown(card, { key: 'Enter' });
      expect(handleClick).toHaveBeenCalledTimes(1);

      fireEvent.keyDown(card, { key: ' ' });
      expect(handleClick).toHaveBeenCalledTimes(2);
    });

    it('renders Panel with header, content, and footer', () => {
      render(
        <Panel
          header={<div>Panel Header</div>}
          footer={<div>Panel Footer</div>}
        >
          <div>Body Content</div>
        </Panel>
      );
      expect(screen.getByText('Panel Header')).toBeInTheDocument();
      expect(screen.getByText('Body Content')).toBeInTheDocument();
      expect(screen.getByText('Panel Footer')).toBeInTheDocument();
    });
  });

  describe('Tabs', () => {
    it('renders tabs and changes active tab on click', () => {
      const handleChange = vi.fn();
      const tabs = [
        { id: 'tab1', label: 'Overview' },
        { id: 'tab2', label: 'Details' },
      ];
      render(<Tabs items={tabs} activeId="tab1" onChange={handleChange} />);

      const tabList = screen.getByRole('tablist');
      expect(tabList).toBeInTheDocument();

      const tab1 = screen.getByRole('tab', { name: 'Overview' });
      const tab2 = screen.getByRole('tab', { name: 'Details' });

      expect(tab1).toHaveAttribute('aria-selected', 'true');
      expect(tab2).toHaveAttribute('aria-selected', 'false');

      fireEvent.click(tab2);
      expect(handleChange).toHaveBeenCalledWith('tab2');
    });
  });

  describe('ProgressBar & Skeleton & Spinner', () => {
    it('renders ProgressBar with value', () => {
      render(<ProgressBar value={45} max={100} />);
      const bar = screen.getByRole('progressbar');
      expect(bar).toHaveAttribute('aria-valuenow', '45');
      expect(bar).toHaveAttribute('aria-valuemax', '100');
    });

    it('renders Skeleton with aria-hidden', () => {
      render(<Skeleton width={200} height={20} data-testid="skeleton" />);
      const sk = screen.getByTestId('skeleton');
      expect(sk).toHaveAttribute('aria-hidden', 'true');
    });

    it('renders Spinner with role status', () => {
      render(<Spinner size={24} />);
      expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
    });
  });

  describe('Alert & EmptyState', () => {
    it('renders Alert with title and children', () => {
      render(
        <Alert type="danger" title="System Error">
          Something failed.
        </Alert>
      );
      const alert = screen.getByRole('alert');
      expect(alert).toHaveTextContent('System Error');
      expect(alert).toHaveTextContent('Something failed.');
      expect(alert.className).toContain('ui-alert--danger');
    });

    it('renders EmptyState with action', () => {
      const handleAction = vi.fn();
      render(
        <EmptyState
          title="No Data"
          description="Please add items."
          action={<button onClick={handleAction}>Add Item</button>}
        />
      );
      expect(screen.getByText('No Data')).toBeInTheDocument();
      expect(screen.getByText('Please add items.')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: 'Add Item' }));
      expect(handleAction).toHaveBeenCalledTimes(1);
    });
  });

  describe('Form Controls & Switch', () => {
    it('renders Input and handles typing', () => {
      const handleChange = vi.fn();
      render(<Input placeholder="Enter title" onChange={handleChange} />);
      const input = screen.getByPlaceholderText('Enter title');
      fireEvent.change(input, { target: { value: 'My Title' } });
      expect(handleChange).toHaveBeenCalled();
    });

    it('renders Switch and handles toggle', () => {
      const handleChange = vi.fn();
      render(<Switch checked={false} onChange={handleChange} label="Enable notifications" />);
      const switchEl = screen.getByRole('switch', { name: 'Enable notifications' });
      expect(switchEl).toHaveAttribute('aria-checked', 'false');

      fireEvent.click(switchEl);
      expect(handleChange).toHaveBeenCalledWith(true);

      fireEvent.keyDown(switchEl, { key: 'Enter' });
      expect(handleChange).toHaveBeenCalledWith(true);
    });

    it('renders Checkbox with label', () => {
      const handleChange = vi.fn();
      render(<Checkbox label="I agree" onChange={handleChange} />);
      const cb = screen.getByRole('checkbox', { name: 'I agree' });
      fireEvent.click(cb);
      expect(handleChange).toHaveBeenCalled();
    });
  });

  describe('Modal & Dialog', () => {
    it('renders Modal when open and closes on Escape', () => {
      const handleClose = vi.fn();
      render(
        <Modal isOpen={true} onClose={handleClose} title="Confirm Delete">
          <div>Are you sure?</div>
        </Modal>
      );
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByText('Confirm Delete')).toBeInTheDocument();

      fireEvent.keyDown(document, { key: 'Escape' });
      expect(handleClose).toHaveBeenCalledTimes(1);
    });

    it('does not render Modal when isOpen is false', () => {
      render(
        <Modal isOpen={false} onClose={() => {}} title="Closed">
          <div>Content</div>
        </Modal>
      );
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  describe('Table & Layout Components', () => {
    it('renders Table rows and headers', () => {
      const columns = [
        { key: 'name', header: 'Name' },
        { key: 'role', header: 'Role' },
      ];
      const data = [
        { id: '1', name: 'Alice', role: 'Admin' },
        { id: '2', name: 'Bob', role: 'User' },
      ];
      render(<Table columns={columns} data={data} keyExtractor={(r) => r.id} />);
      expect(screen.getByText('Name')).toBeInTheDocument();
      expect(screen.getByText('Alice')).toBeInTheDocument();
      expect(screen.getByText('Bob')).toBeInTheDocument();
    });

    it('renders SectionHeader and PageHeader', () => {
      render(
        <div>
          <PageHeader title="Dashboard" description="Overview of system" />
          <SectionHeader title="Active Tasks" subtitle="Tasks in progress" />
        </div>
      );
      expect(screen.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument();
      expect(screen.getByText('Overview of system')).toBeInTheDocument();
      expect(screen.getByText('Active Tasks')).toBeInTheDocument();
      expect(screen.getByText('Tasks in progress')).toBeInTheDocument();
    });

    it('renders Stack and Grid layout containers', () => {
      render(
        <Stack direction="horizontal" gap={12} data-testid="stack">
          <Grid columns={3} gap={8} data-testid="grid">
            <div>Item 1</div>
            <div>Item 2</div>
          </Grid>
        </Stack>
      );
      expect(screen.getByTestId('stack')).toBeInTheDocument();
      expect(screen.getByTestId('grid')).toBeInTheDocument();
    });
  });
});
