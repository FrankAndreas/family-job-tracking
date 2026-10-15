import { STATUS_COLORS, STATUS_LABELS } from '../labels';
import type { Status } from '../types';

export default function StatusBadge({ status }: { status: Status }) {
    return (
        <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold text-white ${STATUS_COLORS[status]}`}>
            {STATUS_LABELS[status]}
        </span>
    );
}
