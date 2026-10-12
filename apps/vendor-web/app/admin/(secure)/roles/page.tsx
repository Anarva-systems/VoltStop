"use client";

import { AdminCard, AdminLoad, AdminPage, useAdminQuery, useAdminToken } from "@/components/admin-ui";
type Role={name:string;description:string;permissions:string[]};
export default function RolesPage(){const token=useAdminToken();const q=useAdminQuery<Role[]>("/roles",token);return <><AdminPage title="Roles & permissions" description="Permission grants are stored on the server and checked on every sensitive API request. Browser role claims are ignored."/><AdminLoad loading={q.loading} error={q.error} data={q.data} retry={q.reload} empty={Boolean(q.data&&!q.data.length)}>{(roles)=><div className="admin-grid-2">{roles.map((role)=><AdminCard key={role.name} title={role.name.replaceAll("_"," ")} subtitle={role.description}><div className="admin-permissions">{role.permissions.map((permission)=><span key={permission}>{permission}</span>)}</div></AdminCard>)}</div>}</AdminLoad></>;}
