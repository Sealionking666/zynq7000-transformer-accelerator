#ifndef HAR_NET_LIFECYCLE_H
#define HAR_NET_LIFECYCLE_H
#include "har_net_pl.h"
enum { HAR_DEV_UNINIT=0, HAR_DEV_READY=1, HAR_DEV_RUNNING=2, HAR_DEV_FAULTED=3 };
/* Single core, single serialized caller. No interrupt/reentrant use.
 * A timeout retains device ownership of ctx and the input allocation.
 * Keep them allocated and unchanged until explicit drain returns OK or
 * PL reconfiguration plus CPU reset ends the old transaction.
 * recover never returns the late logits, never restarts, and does not reset PL.
 * Non-timeout hardware/status/guard faults require that external reset flow.
 */
int har_net_recover(har_net_ctx *s);
int har_net_device_state(void);
#endif
