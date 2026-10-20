import { REJECTION_LABELS, STATUS_COLORS, STATUS_LABELS } from '../labels';
import type { EventType, Status } from '../types';

interface Props {
    status: Status;
    closedBy?: EventType | null; // names the kind of rejection
}

export default function StatusBadge({ status, closedBy }: Props) {
    const label = (status === 'closed_rejection' && closedBy && REJECTION_LABELS[closedBy]) || STATUS_LABELS[status];
    return (
        <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold text-white ${STATUS_COLORS[status]}`}>
            {label}
        </span>
    );
}
