/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

/*!
 * \file src/pass/dispatch_dialect.cc
 * \brief Dispatch the base ops to device-specific dialect ops based on predefined plevels. Note
 * that some ops such as VM related ops do not have dialect ops, and they will remain the same after
 * this pass.
 */
#include <vector>
#include "mnm/device.h"
#include "mnm/op.h"
#include "mnm/ir.h"
#include "mnm/pass.h"

namespace mnm {
namespace pass {
namespace dispatch_dialect {

using namespace mnm::ir;
using namespace mnm::op;

class DispatchMutator : public MixedModeMutator {
 public:
  DispatchMutator(DevType dev_type) : dev_type_(dev_type) {
  }

  Expr VisitExpr_(const FunctionNode* node) final {
    if (node->HasNonzeroAttr(attr::kPrimitive)) {
      // Don't go into fused functions
      return GetRef<Function>(node);
    }
    return ExprMutator::VisitExpr_(node);
  }

  Expr VisitExpr_(const OpNode* node) final {
    auto op = GetRef<Op>(node);
    if (!IsDialectOp(op)) {
      auto dialect_op = OpDialect::Dispatch(op, dev_type_, {});
      if (dialect_op.defined()) {
        return dialect_op;
      }
    }
    return op;
  }

 private:
  DevType dev_type_;
};

Expr Dispatch(const Expr& expr) {
  auto dev = Device::Current(true);
  if (dev->device_type == DevType::kUnknown() || dev->device_id < 0) {
    LOG(WARNING) << "Device is not specified, skip DispatchDialect pass.";
    return expr;
  }
  DevType dev_type = dev.device_type();
  return DispatchMutator(dev_type).Mutate(expr);
}

}  // namespace dispatch_dialect

Pass DispatchDialect() {
  TypedPackedFunc<Function(Function, IRModule, PassContext)> pass_func = [=](Function f, IRModule m,
                                                                             PassContext pc) {
    return Downcast<Function>(dispatch_dialect::Dispatch(f));
  };
  return CreateMNMFunctionPass(pass_func, 1, "DispatchDialect", {});
}

MNM_REGISTER_GLOBAL("mnm.pass_.DispatchDialect").set_body_typed(DispatchDialect);

}  // namespace pass
}  // namespace mnm
